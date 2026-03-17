"""Tests for external dependency import transforms in the app compiler."""
import pytest
from src.services.app_compiler import AppCompilerService


@pytest.fixture
def compiler():
    return AppCompilerService()


@pytest.mark.asyncio
async def test_named_import_transforms_to_deps(compiler):
    """import { X, Y } from "recharts" → const { X, Y } = $deps["recharts"];"""
    source = '''
import { LineChart, Line } from "recharts";
export default function Chart() {
    return <LineChart><Line dataKey="value" /></LineChart>;
}
'''
    result = await compiler.compile_file(source, "pages/chart.tsx")
    assert result.success
    assert '$deps["recharts"]' in result.compiled
    assert "import " not in result.compiled  # no raw imports left


@pytest.mark.asyncio
async def test_default_import_transforms_to_deps(compiler):
    """import X from "dayjs" → const X = ($deps["dayjs"].default || $deps["dayjs"]);"""
    source = '''
import dayjs from "dayjs";
export default function Page() {
    return <div>{dayjs().format("MMM D")}</div>;
}
'''
    result = await compiler.compile_file(source, "pages/index.tsx")
    assert result.success
    assert '$deps["dayjs"]' in result.compiled


@pytest.mark.asyncio
async def test_namespace_import_transforms_to_deps(compiler):
    """import * as R from "recharts" → const R = $deps["recharts"];"""
    source = '''
import * as R from "recharts";
export default function Chart() {
    return <R.LineChart><R.Line /></R.LineChart>;
}
'''
    result = await compiler.compile_file(source, "pages/chart.tsx")
    assert result.success
    assert '$deps["recharts"]' in result.compiled


@pytest.mark.asyncio
async def test_mixed_import_transforms_to_deps(compiler):
    """import X, { Y } from "pkg" → default + named destructuring."""
    source = '''
import Pkg, { Helper } from "some-pkg";
export default function Page() {
    return <div><Pkg /><Helper /></div>;
}
'''
    result = await compiler.compile_file(source, "pages/index.tsx")
    assert result.success
    assert '$deps["some-pkg"]' in result.compiled


@pytest.mark.asyncio
async def test_bifrost_imports_unchanged(compiler):
    """Bifrost imports should still use $ scope, not $deps."""
    source = '''
import { Button, Card } from "bifrost";
export default function Page() {
    return <Card><Button>Click</Button></Card>;
}
'''
    result = await compiler.compile_file(source, "pages/index.tsx")
    assert result.success
    assert "var {" in result.compiled or "var " in result.compiled
    assert "= $;" in result.compiled or "= $" in result.compiled
    assert "$deps" not in result.compiled


@pytest.mark.asyncio
async def test_mixed_bifrost_and_external_imports(compiler):
    """Bifrost and external imports coexist."""
    source = '''
import { Card, useWorkflowQuery } from "bifrost";
import { LineChart, Line } from "recharts";
import dayjs from "dayjs";

export default function Dashboard() {
    const { data } = useWorkflowQuery("get_metrics");
    return (
        <Card>
            <p>{dayjs().format("MMM D")}</p>
            <LineChart data={data}><Line dataKey="value" /></LineChart>
        </Card>
    );
}
'''
    result = await compiler.compile_file(source, "pages/dashboard.tsx")
    assert result.success
    assert "= $;" in result.compiled  # bifrost imports
    assert '$deps["recharts"]' in result.compiled
    assert '$deps["dayjs"]' in result.compiled


@pytest.mark.asyncio
async def test_relative_imports_are_stripped(compiler):
    """Relative imports (custom components, same-app modules) must be stripped, not turned into $deps."""
    source = '''
import { StatusBadge } from "../../components/StatusBadge";
import Header from "../components/Header";
import * as Utils from "./utils";
export default function Page() {
    return <div><StatusBadge /><Header /></div>;
}
'''
    result = await compiler.compile_file(source, "pages/overview.tsx")
    assert result.success
    assert "$deps" not in result.compiled
    assert "StatusBadge" not in result.compiled or "import" not in result.compiled
    # The component references in JSX should still be there
    assert "StatusBadge" in result.compiled


@pytest.mark.asyncio
async def test_relative_imports_mixed_with_bifrost_and_npm(compiler):
    """Relative imports are stripped while bifrost and npm imports are preserved."""
    source = '''
import { Card } from "bifrost";
import { LineChart } from "recharts";
import { StatusBadge } from "../../components/StatusBadge";
export default function Page() {
    return <Card><LineChart /><StatusBadge /></Card>;
}
'''
    result = await compiler.compile_file(source, "pages/index.tsx")
    assert result.success
    assert "= $;" in result.compiled  # bifrost
    assert '$deps["recharts"]' in result.compiled  # npm
    assert '$deps["../../components/StatusBadge"]' not in result.compiled  # NOT in $deps


@pytest.mark.asyncio
async def test_no_imports_compiles_normally(compiler):
    """Files with no imports should compile without $deps references."""
    source = '''
export default function Page() {
    return <div>Hello</div>;
}
'''
    result = await compiler.compile_file(source, "pages/index.tsx")
    assert result.success
    assert "$deps" not in result.compiled
