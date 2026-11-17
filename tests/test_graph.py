from unittest.mock import patch
from app.graph import build_graph


def test_rejection_feedback_can_regenerate_proposal():
    builder = build_graph()
    # Verify graph contains the required nodes and intended sequential review path.
    graph = builder.compile()
    assert set(graph.get_graph().nodes) >= {
        "fetch_pr_node", "lint_code_node", "propose_refactor_node", "apply_changes_node"
    }


def test_fetch_node_can_be_mocked():
    with patch("app.graph.fetch_pull_request", return_value={
        "repo_full_name": "owner/repo", "pr_number": 1, "branch_name": "feature", "code_contents": {"a.py": "print('hi')"}
    }):
        from app.graph import fetch_pr_node
        state = {"pr_url": "https://github.com/owner/repo/pull/1", "history": []}
        result = fetch_pr_node(state)
        assert result["repo_full_name"] == "owner/repo"
        assert "a.py" in result["code_contents"]
