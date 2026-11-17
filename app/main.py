from uuid import uuid4
from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
from langgraph.types import Command
from .graph import graph

app = FastAPI(title="Autonomous Code Review & Refactoring Agent", version="1.0.0")


class WebhookPayload(BaseModel):
    pr_url: str | None = None
    repository_url: str | None = None
    pull_request_number: int | None = None
    branch_name: str | None = None
    pull_request: dict | None = None
    action: str | None = None


class ApprovalPayload(BaseModel):
    approved: bool
    feedback: str | None = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/webhooks/github")
def github_webhook(payload: WebhookPayload):
    pr_url = str(payload.pr_url or "")
    if not pr_url and payload.pull_request:
        pr_url = payload.pull_request.get("html_url", "")
    if not pr_url and payload.repository_url and payload.pull_request_number:
        pr_url = f"{payload.repository_url.rstrip('/')}/pull/{payload.pull_request_number}"
    if not pr_url:
        raise HTTPException(status_code=400, detail="Provide pr_url, or repository_url plus pull_request_number, or a GitHub pull_request payload with html_url")
    thread_id = str(uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    initial_state = {"pr_url": pr_url, "is_approved": False, "reviewer_feedback": "", "history": []}
    try:
        result = graph.invoke(initial_state, config=config)
        snapshot = graph.get_state(config)
        return {"thread_id": thread_id, "status": result.get("status", "paused"), "next": list(snapshot.next), "state": snapshot.values}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/reviews/{thread_id}/approve")
def review_decision(thread_id: str, payload: ApprovalPayload):
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = graph.get_state(config)
    if not snapshot.values:
        raise HTTPException(status_code=404, detail="Review thread not found")
    try:
        if payload.approved:
            graph.update_state(config, {"is_approved": True, "reviewer_feedback": "", "status": "approved"})
        else:
            if not payload.feedback:
                raise HTTPException(status_code=400, detail="feedback is required when approved=false")
            # Rewind to the edge after linting so the next invocation regenerates the proposal.
            graph.update_state(
                config,
                {"is_approved": False, "reviewer_feedback": payload.feedback, "status": "revision_requested"},
                as_node="lint_code_node",
            )
        result = graph.invoke(None, config=config)
        current = graph.get_state(config)
        return {"thread_id": thread_id, "status": result.get("status", "paused"), "next": list(current.next), "state": current.values}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
