# Autonomous Code Review & Refactoring Agent

A LangGraph-powered workflow that fetches Python files from a GitHub Pull Request, runs lint checks, proposes an AI-assisted refactor, pauses for human approval, and commits approved changes to the PR branch.

## Requirements
- Python 3.11+
- Git
- GitHub token with repository contents and pull request read/write permissions
- OpenAI API key

## Setup

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Add `GITHUB_TOKEN` and `OPENAI_API_KEY` to `.env`. Never commit `.env`.

## Run

```bash
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the interactive API documentation.

## Start a review

```bash
curl -X POST http://127.0.0.1:8000/api/webhooks/github \\
  -H 'Content-Type: application/json' \\
  -d '{"pr_url":"https://github.com/OWNER/REPOSITORY/pull/1"}'
```

Save the returned `thread_id`. The graph pauses before any Git write.

## Approve

```bash
curl -X POST http://127.0.0.1:8000/api/reviews/THREAD_ID/approve \\
  -H 'Content-Type: application/json' \\
  -d '{"approved":true}'
```

## Request changes

```bash
curl -X POST http://127.0.0.1:8000/api/reviews/THREAD_ID/approve \\
  -H 'Content-Type: application/json' \\
  -d '{"approved":false,"feedback":"Use list comprehensions instead of loops"}'
```

## Tests

```bash
pytest -q
```

## Safety notes
- The linter writes candidate source to a temporary directory and runs Flake8/Black against the file. It does not execute candidate Python code.
- GitHub writes happen only after an explicit approval request.
- Use a test repository first. Review generated diffs before approving.
- For production deployment, add webhook signature verification, authentication on review endpoints, rate limits, and a stronger isolated container runner.

## Architecture

`fetch_pr_node -> lint_code_node -> propose_refactor_node -> [interrupt before apply_changes_node] -> apply_changes_node`

A rejection updates the persisted thread and rewinds execution to the lint-to-refactor transition so a new proposal incorporates reviewer feedback. An approval resumes the paused thread and permits the GitHub commit.
