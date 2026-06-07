import textwrap
from pathlib import Path

from bifrost.solution_dev.function_host import discover_functions


def _write(p: Path, body: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(body))


def test_discovers_decorated_functions_in_arbitrary_folders(tmp_path: Path):
    (tmp_path / "bifrost.solution.yaml").write_text("slug: demo\nname: Demo\nscope: org\n")
    _write(tmp_path / "functions/hello.py", '''
        from bifrost import workflow

        @workflow
        async def main():
            return {"message": "hi"}
    ''')
    _write(tmp_path / "modules/sub/calc.py", '''
        from bifrost import workflow

        @workflow
        async def add():
            return {"ok": True}
    ''')

    fns = discover_functions(tmp_path)

    assert "functions/hello.py::main" in fns
    assert "modules/sub/calc.py::add" in fns
    assert callable(fns["functions/hello.py::main"])
