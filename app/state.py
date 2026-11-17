from typing import TypedDict, Any


class ReviewState(TypedDict, total=False):
    pr_url: str
    repo_full_name: str
    pr_number: int
    branch_name: str
    code_contents: dict[str, str]
    lint_errors: dict[str, str]
    refactored_code: dict[str, str]
    is_approved: bool
    reviewer_feedback: str
    history: list[dict[str, Any]]
    commit_sha: str
    status: str
