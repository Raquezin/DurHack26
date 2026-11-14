import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "navigator"

LAYERS = ("domain", "ports", "application", "adapters", "bootstrap")


def _layer(path: Path) -> str | None:
    rel = path.relative_to(SRC)
    return rel.parts[0] if rel.parts[0] in LAYERS else None


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            names.add(node.module or "")
    return names


def _navigator_imports(path: Path) -> set[str]:
    return {n for n in _imports(path) if n.split(".")[0] == "navigator"}


def _layer_of(module: str) -> str | None:
    parts = module.split(".")
    if len(parts) >= 2 and parts[1] in LAYERS:
        return parts[1]
    return None


def _files():
    return sorted(SRC.rglob("*.py"))


def test_domain_imports_stdlib_only():
    for path in _files():
        if _layer(path) != "domain":
            continue
        for module in _imports(path):
            top = module.split(".")[0]
            if top == "navigator":
                layer = _layer_of(module)
                assert layer in (None, "domain"), f"{path}: {module}"
            else:
                assert top in sys.stdlib_module_names, f"{path}: {module}"


def test_ports_import_only_domain():
    for path in _files():
        if _layer(path) != "ports":
            continue
        for module in _navigator_imports(path):
            assert _layer_of(module) in (None, "domain", "ports"), (
                f"{path}: {module}"
            )


def test_application_imports_domain_and_ports():
    for path in _files():
        if _layer(path) != "application":
            continue
        for module in _navigator_imports(path):
            assert _layer_of(module) in (
                None,
                "domain",
                "ports",
                "application",
            ), f"{path}: {module}"


def test_adapters_never_import_application_bootstrap_or_siblings():
    for path in _files():
        if _layer(path) != "adapters":
            continue
        own = path.relative_to(SRC).parts[1]
        for module in _navigator_imports(path):
            layer = _layer_of(module)
            assert layer in (None, "domain", "ports", "adapters"), (
                f"{path}: {module}"
            )
            if layer == "adapters":
                assert module.split(".")[2] == own, f"{path}: {module}"
