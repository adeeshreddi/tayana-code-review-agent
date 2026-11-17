from app.tools import run_linter_tool


def test_linter_flags_syntax_error():
    result = run_linter_tool.invoke({"code_string": "def broken(:\n    pass\n"})
    assert "candidate.py" in result or "SyntaxError" in result or "E999" in result
