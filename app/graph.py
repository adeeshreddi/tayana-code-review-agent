import os
from typing import Any
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_openai import ChatOpenAI
from .state import ReviewState
from .github_client import fetch_pull_request, commit_files
from .tools import run_linter_tool


def _history(state: ReviewState, event: str, details: Any = None) -> list[dict]:
    return state.get("history", []) + [{"event": event, "details": details}]


def fetch_pr_node(state: ReviewState) -> dict:
    pr = fetch_pull_request(state["pr_url"])
    return {**pr, "status": "fetched", "history": _history(state, "fetched_pr", list(pr["code_contents"].keys()))}


def lint_code_node(state: ReviewState) -> dict:
    results = {name: run_linter_tool.invoke({"code_string": code}) for name, code in state.get("code_contents", {}).items()}
    return {"lint_errors": results, "status": "linted", "history": _history(state, "lint_completed", results)}


def propose_refactor_node(state: ReviewState) -> dict:
    if not state.get("code_contents"):
        return {"refactored_code": {}, "status": "no_python_files", "history": _history(state, "no_python_files")}
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required to generate refactoring proposals")
    model = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), temperature=0)
    proposed: dict[str, str] = {}
    for filename, original in state["code_contents"].items():
        lint_output = state.get("lint_errors", {}).get(filename, "No lint output")
        feedback = state.get("reviewer_feedback", "No reviewer feedback yet")
        prompt = (
            "You are a careful Python refactoring assistant. Return ONLY the complete replacement Python source code, "
            "without Markdown fences. Preserve behavior and public interfaces. Fix relevant lint issues. "
            "Incorporate reviewer feedback when present. If no meaningful change is needed, return the original code.\n\n"
            f"Filename: {filename}\nLint results:\n{lint_output}\nReviewer feedback:\n{feedback}\n\nOriginal code:\n{original}"
        )
        response = model.invoke(prompt)
        proposed[filename] = response.content if isinstance(response.content, str) else str(response.content)
    return {"refactored_code": proposed, "is_approved": False, "status": "awaiting_approval", "history": _history(state, "refactor_proposed", list(proposed.keys()))}


def apply_changes_node(state: ReviewState) -> dict:
    if not state.get("is_approved"):
        return {"status": "approval_required", "history": _history(state, "write_blocked_no_approval")}
    sha = commit_files(
        state["repo_full_name"], state["branch_name"], state.get("refactored_code", {}),
        f"Apply AI-assisted refactoring for PR #{state.get('pr_number', '')}",
    )
    return {"commit_sha": sha, "status": "completed", "history": _history(state, "changes_committed", sha)}


def build_graph():
    builder = StateGraph(ReviewState)
    builder.add_node("fetch_pr_node", fetch_pr_node)
    builder.add_node("lint_code_node", lint_code_node)
    builder.add_node("propose_refactor_node", propose_refactor_node)
    builder.add_node("apply_changes_node", apply_changes_node)
    builder.set_entry_point("fetch_pr_node")
    builder.add_edge("fetch_pr_node", "lint_code_node")
    builder.add_edge("lint_code_node", "propose_refactor_node")
    builder.add_edge("propose_refactor_node", "apply_changes_node")
    builder.add_edge("apply_changes_node", END)
    return builder


# SQLite provides persistence across server restarts. The connection is kept open for app lifetime.
_CHECKPOINT_CONNECTION = None

def compile_graph():
    global _CHECKPOINT_CONNECTION
    import sqlite3
    db_path = os.getenv("CHECKPOINT_DB", "checkpoints.sqlite")
    _CHECKPOINT_CONNECTION = sqlite3.connect(db_path, check_same_thread=False)
    checkpointer = SqliteSaver(_CHECKPOINT_CONNECTION)
    checkpointer.setup()
    return build_graph().compile(checkpointer=checkpointer, interrupt_before=["apply_changes_node"])


graph = compile_graph()
