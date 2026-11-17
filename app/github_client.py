import os
import re
from urllib.parse import quote
import requests

GITHUB_API = "https://api.github.com"


def parse_pr_url(pr_url: str) -> tuple[str, int]:
    match = re.match(r"https?://github\.com/([^/]+/[^/]+)/pull/(\d+)", pr_url.strip())
    if not match:
        raise ValueError("pr_url must look like https://github.com/owner/repo/pull/123")
    return match.group(1), int(match.group(2))


def _headers() -> dict[str, str]:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_pull_request(pr_url: str) -> dict:
    repo, number = parse_pr_url(pr_url)
    response = requests.get(f"{GITHUB_API}/repos/{repo}/pulls/{number}", headers=_headers(), timeout=30)
    response.raise_for_status()
    pr = response.json()
    files_response = requests.get(f"{GITHUB_API}/repos/{repo}/pulls/{number}/files", headers=_headers(), timeout=30)
    files_response.raise_for_status()
    files: dict[str, str] = {}
    for item in files_response.json():
        filename = item.get("filename", "")
        if not filename.endswith(".py") or item.get("status") == "removed":
            continue
        content_response = requests.get(
            f"{GITHUB_API}/repos/{repo}/contents/{filename}",
            headers={**_headers(), "Accept": "application/vnd.github.raw+json"},
            params={"ref": pr.get("head", {}).get("sha", "")},
            timeout=30,
        )
        content_response.raise_for_status()
        files[filename] = content_response.text
    # Write back to the PR head repository (which may be a fork), not always the base repository.
    head_repo = (pr.get("head", {}).get("repo") or {}).get("full_name") or repo
    return {
        "repo_full_name": head_repo,
        "pr_number": number,
        "branch_name": pr.get("head", {}).get("ref", ""),
        "code_contents": files,
    }


def commit_files(repo: str, branch: str, files: dict[str, str], message: str) -> str:
    """Commit approved file contents using the Git Trees API."""
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required to commit changes")
    headers = {**_headers(), "Accept": "application/vnd.github+json"}
    ref_resp = requests.get(f"{GITHUB_API}/repos/{repo}/git/ref/heads/{quote(branch, safe='')}", headers=headers, timeout=30)
    ref_resp.raise_for_status()
    parent_sha = ref_resp.json()["object"]["sha"]
    commit_resp = requests.get(f"{GITHUB_API}/repos/{repo}/git/commits/{parent_sha}", headers=headers, timeout=30)
    commit_resp.raise_for_status()
    base_tree = commit_resp.json()["tree"]["sha"]
    tree_items = [{"path": path, "mode": "100644", "type": "blob", "content": content} for path, content in files.items()]
    tree_resp = requests.post(f"{GITHUB_API}/repos/{repo}/git/trees", headers=headers, json={"base_tree": base_tree, "tree": tree_items}, timeout=30)
    tree_resp.raise_for_status()
    new_tree = tree_resp.json()["sha"]
    new_commit_resp = requests.post(
        f"{GITHUB_API}/repos/{repo}/git/commits", headers=headers,
        json={"message": message, "tree": new_tree, "parents": [parent_sha]}, timeout=30,
    )
    new_commit_resp.raise_for_status()
    new_commit = new_commit_resp.json()["sha"]
    update_resp = requests.patch(
        f"{GITHUB_API}/repos/{repo}/git/refs/heads/{quote(branch, safe='')}", headers=headers,
        json={"sha": new_commit}, timeout=30,
    )
    update_resp.raise_for_status()
    return new_commit
