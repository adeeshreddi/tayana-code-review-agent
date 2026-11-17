import subprocess
import tempfile
from pathlib import Path
from langchain_core.tools import tool


@tool
def run_linter_tool(code_string: str) -> str:
    """Check a Python code string with Flake8 and Black without executing the code."""
    with tempfile.TemporaryDirectory(prefix="code-review-") as temp_dir:
        code_path = Path(temp_dir) / "candidate.py"
        code_path.write_text(code_string, encoding="utf-8")
        results = []
        for command in (["flake8", str(code_path)], ["black", "--check", str(code_path)]):
            try:
                completed = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
                output = (completed.stdout + completed.stderr).strip()
                results.append(f"$ {' '.join(command)}\nexit_code={completed.returncode}\n{output or 'No output'}")
            except FileNotFoundError:
                results.append(f"$ {' '.join(command)}\nTool not installed")
            except subprocess.TimeoutExpired:
                results.append(f"$ {' '.join(command)}\nTimed out")
        return "\n\n".join(results)
