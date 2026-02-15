import pytest
from src.services.app_compiler import AppCompilerService, CompileResult


@pytest.fixture
def compiler():
    return AppCompilerService()


class TestAppCompilerService:
    @pytest.mark.asyncio
    async def test_compile_simple_component(self, compiler):
        source = 'export default function Page() { return <div>Hello</div>; }'
        result = await compiler.compile_file(source, "pages/index.tsx")
        assert result.success is True
        assert result.compiled is not None
        assert "__defaultExport__" in result.compiled
        assert result.error is None

    @pytest.mark.asyncio
    async def test_compile_with_bifrost_imports(self, compiler):
        source = '''import { Button, useState } from "bifrost";
export default function Page() {
  const [count, setCount] = useState(0);
  return <Button onClick={() => setCount(count + 1)}>{count}</Button>;
}'''
        result = await compiler.compile_file(source, "pages/index.tsx")
        assert result.success is True
        assert "const {" in result.compiled or "const { " in result.compiled

    @pytest.mark.asyncio
    async def test_compile_syntax_error(self, compiler):
        source = 'export default function Page() { return <div>; }'
        result = await compiler.compile_file(source, "pages/index.tsx")
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_compile_batch(self, compiler):
        files = [
            {"path": "pages/index.tsx", "source": "export default function A() { return <div>A</div>; }"},
            {"path": "pages/about.tsx", "source": "export default function B() { return <div>B</div>; }"},
        ]
        results = await compiler.compile_batch(files)
        assert len(results) == 2
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_compile_batch_partial_failure(self, compiler):
        files = [
            {"path": "pages/good.tsx", "source": "export default function A() { return <div>A</div>; }"},
            {"path": "pages/bad.tsx", "source": "export default function B() { return <div>; }"},
        ]
        results = await compiler.compile_batch(files)
        assert results[0].success is True
        assert results[1].success is False
