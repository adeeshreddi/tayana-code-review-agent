
from unittest.mock import patch

from langgraph.checkpoint.memory import MemorySaver

from app.graph import build_graph

def test_graph_contains_required_nodes():
    graph = build_graph().compile()

    assert set(graph.get_graph().nodes) >= {
        "fetch_pr_node",
        "lint_code_node",
        "propose_refactor_node",
        "apply_changes_node",
    }

def test_fetch_node_can_be_mocked():
    with patch(
        "app.graph.fetch_pull_request",
        return_value={
            "repo_full_name": "owner/repo",
            "pr_number": 1,
            "branch_name": "feature",
            "code_contents": {"sample.py": "print('hello')"},
        },
    ):
        from app.graph import fetch_pr_node

        state = {
            "pr_url": "https://github.com/owner/repo/pull/1",
            "history": [],
        }

        result = fetch_pr_node(state)

        assert result["repo_full_name"] == "owner/repo"
        assert "sample.py" in result["code_contents"]

def test_rejection_feedback_routes_back_to_refactor():
    observed_feedback = []

    def fake_proposal(state):
        observed_feedback.append(
            state.get("reviewer_feedback", "")
        )
        return {
            "refactored_code": {
                "sample.py": "print('refactored')"
            },
            "is_approved": False,
            "status": "awaiting_approval",
        }

    with (
        patch(
            "app.graph.fetch_pull_request",
            return_value={
                "repo_full_name": "owner/repo",
                "pr_number": 1,
                "branch_name": "feature",
                "code_contents": {
                    "sample.py": "print('hello')"
                },
            },
        ),
        patch(
            "app.graph.run_linter_tool",
            new=type(
               "FakeLinter",
               (),
               {"invoke": lambda self, data: "lint clean"}
            )(),
        ),
        patch(
            "app.graph.propose_refactor_node",
            side_effect=fake_proposal,
        ),
    ):
        workflow = build_graph().compile(
            checkpointer=MemorySaver(),
            interrupt_before=["apply_changes_node"],
        )

        config = {
            "configurable": {
                "thread_id": "test-review-1"
            }
        }

        workflow.invoke(
            {
                "pr_url": "https://github.com/owner/repo/pull/1",
                "is_approved": False,
                "reviewer_feedback": "",
                "history": [],
            },
            config=config,
        )

        snapshot = workflow.get_state(config)

        assert snapshot.next == ("apply_changes_node",)
        assert observed_feedback == [""]

        workflow.update_state(
            config,
            {
                "is_approved": False,
                "reviewer_feedback": "Please simplify this code.",
            },
            as_node="lint_code_node",
        )

        workflow.invoke(None, config=config)

        snapshot = workflow.get_state(config)

        assert snapshot.next == ("apply_changes_node",)
        assert observed_feedback == [
            "",
            "Please simplify this code.",
        ]
        assert snapshot.values["reviewer_feedback"] == (
            "Please simplify this code."
        )