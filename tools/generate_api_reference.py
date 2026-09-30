"""Generate a browsable API reference from the repository's Python docstrings."""

from __future__ import annotations

import argparse
import ast
import re
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "api-reference.md"
SOURCE_DIRECTORIES = (ROOT / "src", ROOT / "tests", ROOT / "tools")
SECTION_NAMES = {
    "Args",
    "Arguments",
    "Parameters",
    "Returns",
    "Raises",
    "Yields",
    "Notes",
    "Examples",
}


def _python_files() -> list[Path]:
    """Return application, test, and documentation-tool modules in stable order."""
    paths = [ROOT / "main.py"]
    for directory in SOURCE_DIRECTORIES:
        paths.extend(directory.rglob("*.py"))
    return sorted(paths, key=lambda path: path.relative_to(ROOT).as_posix())


def _definitions(node: ast.AST, scope: tuple[str, ...] = ()):
    """Yield each named class and function, including definitions nested in callables."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.ClassDef):
            qualified_name = (*scope, child.name)
            yield child, "class", qualified_name
            yield from _definitions(child, qualified_name)
        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qualified_name = (*scope, child.name)
            yield child, "function", qualified_name
            yield from _definitions(child, qualified_name)
        else:
            yield from _definitions(child, scope)


def _argument_text(argument: ast.arg) -> str:
    """Render one parameter name and its declared type without evaluating defaults."""
    if argument.annotation is None:
        return argument.arg
    return f"{argument.arg}: {ast.unparse(argument.annotation)}"


def _signature(
    node: ast.FunctionDef | ast.AsyncFunctionDef, qualified_name: str
) -> str:
    """Render a callable's complete annotated signature for Markdown display."""
    arguments = node.args
    positional = [*arguments.posonlyargs, *arguments.args]
    default_start = len(positional) - len(arguments.defaults)
    rendered = []

    for index, argument in enumerate(positional):
        item = _argument_text(argument)
        if index >= default_start:
            item += f" = {ast.unparse(arguments.defaults[index - default_start])}"
        rendered.append(item)
        if arguments.posonlyargs and index == len(arguments.posonlyargs) - 1:
            rendered.append("/")

    if arguments.vararg is not None:
        rendered.append(f"*{_argument_text(arguments.vararg)}")
    elif arguments.kwonlyargs:
        rendered.append("*")

    for argument, default in zip(
        arguments.kwonlyargs, arguments.kw_defaults, strict=True
    ):
        item = _argument_text(argument)
        if default is not None:
            item += f" = {ast.unparse(default)}"
        rendered.append(item)

    if arguments.kwarg is not None:
        rendered.append(f"**{_argument_text(arguments.kwarg)}")

    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    signature = f"{prefix} {qualified_name}({', '.join(rendered)})"
    if node.returns is not None:
        signature += f" -> {ast.unparse(node.returns)}"
    return signature


def _render_docstring(docstring: str) -> list[str]:
    """Format a cleaned Python docstring as readable Markdown prose and lists."""
    output = []
    section = None
    for line in textwrap.dedent(docstring).strip().splitlines():
        stripped = line.strip()
        if not stripped:
            output.append("")
        elif stripped.endswith(":") and stripped[:-1] in SECTION_NAMES:
            section = stripped[:-1]
            output.extend(("", f"**{section}**"))
        elif section and line[:1].isspace():
            parameter = re.match(r"([^:]+):\s*(.*)", stripped)
            if parameter:
                output.append(f"- **`{parameter.group(1)}`** — {parameter.group(2)}")
            else:
                output.append(f"  {stripped}")
        else:
            section = None
            output.append(stripped)
    return output


def render_reference() -> str:
    """Build the complete module, class, and callable reference from source files."""
    lines = [
        "# Botfragg API reference",
        "",
        "This reference covers every Python module, class, and named function in the application, tests, and documentation tools. It is generated from the source docstrings; edit those docstrings and regenerate this page when behavior or signatures change.",
        "",
    ]

    for path in _python_files():
        relative_path = path.relative_to(ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative_path)
        module_doc = ast.get_docstring(tree)
        if module_doc is None:
            raise ValueError(f"Missing module docstring: {relative_path}")

        lines.extend((f"## `{relative_path}`", "", *_render_docstring(module_doc), ""))
        for node, kind, scope in _definitions(tree):
            docstring = ast.get_docstring(node)
            if docstring is None:
                raise ValueError(
                    f"Missing docstring: {relative_path}:{node.lineno} ({'.'.join(scope)})"
                )

            source_link = f"../{relative_path}#L{node.lineno}"
            parent_scope = ".".join(scope[:-1]) or "module"
            scope_label = f"**Scope:** `{relative_path}` · `{parent_scope}`"
            if kind == "class":
                bases = (
                    f"({', '.join(ast.unparse(base) for base in node.bases)})"
                    if node.bases
                    else ""
                )
                heading = f"### `class {node.name}{bases}`"
            else:
                heading = f"### `{_signature(node, node.name)}`"
            lines.extend(
                (
                    heading,
                    "",
                    scope_label,
                    "",
                    f"[Source]({source_link})",
                    "",
                    *_render_docstring(docstring),
                    "",
                )
            )

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    """Write the API reference or verify it matches the current source docstrings."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when docs/api-reference.md is not up to date",
    )
    args = parser.parse_args()
    rendered = render_reference()

    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != rendered:
            parser.error(
                "docs/api-reference.md is out of date; run this command without --check"
            )
        print("docs/api-reference.md is up to date")
        return 0

    OUTPUT.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
