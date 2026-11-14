import ast
import io
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS = [ROOT / name for name in ("src", "tests", "bench")]


def _python_files():
    for base in SCAN_DIRS:
        if base.exists():
            yield from sorted(base.rglob("*.py"))


def test_no_comment_tokens():
    offenders = []
    for path in _python_files():
        text = path.read_text()
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                if tok.start[0] == 1 and tok.string.startswith("#!"):
                    continue
                offenders.append(f"{path}:{tok.start[0]}")
    assert not offenders, offenders


def _docstrings(tree):
    bodies = [tree.body]
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bodies.append(node.body)
    for body in bodies:
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            yield body[0]


def test_no_docstrings():
    offenders = []
    for path in _python_files():
        tree = ast.parse(path.read_text())
        for node in _docstrings(tree):
            offenders.append(f"{path}:{node.lineno}")
    assert not offenders, offenders
