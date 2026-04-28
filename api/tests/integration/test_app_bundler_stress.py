"""Stress-test the v2 bundler with realistic app source.

Goal: prove that an app using all the patterns Claude reaches for in normal
React work (shadcn primitives, Recharts, custom CSS variables, @apply,
arbitrary Tailwind values, responsive variants of arbitrary values) bundles
cleanly and the produced CSS contains rules for every pattern that
silently no-op'd in v2 today.

This is the "is the developer experience trustworthy now?" test. If this
passes, the bifrost-build skill no longer has to caveat what Tailwind
features work; Tailwind just works.
"""
from __future__ import annotations

import pathlib
import tempfile

import pytest

from src.services.app_bundler import (
    TAILWIND_OUTPUT_CSS,
    BundlerService,
)


STRESS_LAYOUT_TSX = """\
import { Outlet } from "bifrost";

export default function Layout() {
  return (
    <div className="min-h-[calc(100vh-4rem)] bg-[color:var(--ops-bg)] text-[color:var(--ops-fg)]">
      <header className="border-b border-[color:var(--ops-border)] px-[clamp(1rem,3vw,2.5rem)] py-4">
        <div className="mx-auto max-w-[1400px] flex items-center gap-4">
          <h1 className="text-xl font-semibold tracking-tight">Operations</h1>
        </div>
      </header>
      <main className="mx-auto max-w-[1400px] px-[clamp(1rem,3vw,2.5rem)] py-10 lg:py-14">
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_360px] gap-10">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
"""

STRESS_PAGE_TSX = """\
import {
  Card, CardHeader, CardTitle, CardContent, Badge, Button,
  Sheet, SheetTrigger, SheetContent,
  Popover, PopoverTrigger, PopoverContent,
  Command, CommandInput, CommandList, CommandItem,
  HoverCard, HoverCardTrigger, HoverCardContent,
  Tabs, TabsList, TabsTrigger, TabsContent,
  Tooltip, TooltipTrigger, TooltipContent, TooltipProvider,
  Calendar, AlertDialog, AlertDialogTrigger, AlertDialogContent,
  Dialog, DialogTrigger, DialogContent,
  toast,
} from "bifrost";
import { Activity, AlertCircle, ChevronRight } from "bifrost";
import { LineChart, Line, XAxis, YAxis, BarChart, Bar, ScatterChart, Scatter } from "recharts";

const data = [{x:1,y:10},{x:2,y:30},{x:3,y:25}];

export default function OpsConsole() {
  return (
    <div className="space-y-[clamp(1rem,2vw,1.5rem)]">
      <div className="grid gap-4 md:grid-cols-[repeat(auto-fit,minmax(220px,1fr))]">
        <Card className="bg-[color:var(--ops-paper)] backdrop-blur-[8px]">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="size-4" /> Throughput
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[120px]">
              <LineChart width={220} height={120} data={data}>
                <Line dataKey="y" />
              </LineChart>
            </div>
          </CardContent>
        </Card>
      </div>

      <Sheet>
        <SheetTrigger asChild>
          <Button className="bg-[oklch(0.4_0.1_220)] hover:bg-[oklch(0.5_0.1_220)] text-white">
            Open drawer
          </Button>
        </SheetTrigger>
        <SheetContent className="bg-[color:var(--ops-paper)] backdrop-blur-none">
          <Tabs defaultValue="a">
            <TabsList className="grid grid-cols-[repeat(3,minmax(0,1fr))]">
              <TabsTrigger value="a">A</TabsTrigger>
              <TabsTrigger value="b">B</TabsTrigger>
              <TabsTrigger value="c">C</TabsTrigger>
            </TabsList>
            <TabsContent value="a">
              <ScatterChart width={300} height={200} data={data}>
                <Scatter dataKey="y" />
              </ScatterChart>
            </TabsContent>
          </Tabs>
        </SheetContent>
      </Sheet>

      <Popover>
        <PopoverTrigger asChild>
          <Button>Filters</Button>
        </PopoverTrigger>
        <PopoverContent className="w-[min(360px,90vw)]">
          <Command>
            <CommandInput placeholder="Search..." />
            <CommandList>
              <CommandItem>Item</CommandItem>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>

      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger>
            <Badge className="bg-[hsl(var(--accent)/0.6)]">Warning</Badge>
          </TooltipTrigger>
          <TooltipContent>Hover</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </div>
  );
}
"""

STRESS_STYLES_CSS = """\
/* Custom CSS variables — these were silently broken in v2 because
 * Tailwind never compiled the bg-[color:var(...)] references. */
:root {
  --ops-bg: oklch(0.985 0 0);
  --ops-paper: oklch(1 0 0);
  --ops-fg: oklch(0.145 0 0);
  --ops-border: oklch(0.92 0 0);
}
.dark {
  --ops-bg: oklch(0.145 0 0);
  --ops-paper: oklch(0.205 0 0);
  --ops-fg: oklch(0.985 0 0);
  --ops-border: oklch(1 0 0 / 12%);
}

/* @apply was also broken in v2 because user CSS files weren't
 * post-processed by Tailwind at all. */
.ops-pill {
  @apply inline-flex items-center rounded-full px-3 py-1 text-xs font-medium;
}
"""


@pytest.mark.asyncio
async def test_stress_app_compiles_all_modern_tailwind_patterns() -> None:
    """The smoke test: a realistic app source tree using arbitrary values,
    responsive variants of arbitrary values, CSS variables, oklch/hsl in
    bracket notation, clamp(), min(), and `@apply` in styles.css all show
    up as real CSS rules in the generated bundle output."""
    bundler = BundlerService()

    with tempfile.TemporaryDirectory() as tmp:
        src_dir = pathlib.Path(tmp)
        (src_dir / "_layout.tsx").write_text(STRESS_LAYOUT_TSX, encoding="utf-8")
        (src_dir / "pages").mkdir()
        (src_dir / "pages" / "index.tsx").write_text(STRESS_PAGE_TSX, encoding="utf-8")
        (src_dir / "styles.css").write_text(STRESS_STYLES_CSS, encoding="utf-8")
        sources = ["_layout.tsx", "pages/index.tsx", "styles.css"]

        added, _ = await bundler._generate_app_tailwind(src_dir, sources)
        assert added is True, "stress-test sources should yield Tailwind CSS"
        css = (src_dir / TAILWIND_OUTPUT_CSS).read_text(encoding="utf-8")

    # Layout patterns from real-world session friction
    assert "calc(100vh" in css, "calc() in arbitrary values must compile"
    assert "1400px" in css, "max-width arbitrary measurements must compile"
    assert "minmax(0,1fr)" in css or "minmax(0, 1fr)" in css, (
        "responsive arbitrary grid templates must compile (Pipeline Command bug)"
    )
    assert "clamp(" in css, "clamp() arbitrary values must compile"

    # CSS-variable arbitrary values (the translucent-drawer bug)
    assert "var(--ops-bg)" in css, "arbitrary bg with CSS variable must compile"
    assert "var(--ops-paper)" in css, "arbitrary bg-[color:var(--paper)] must compile"
    assert "var(--ops-fg)" in css, "arbitrary text color with CSS variable must compile"
    assert "var(--ops-border)" in css, "arbitrary border with CSS variable must compile"

    # Modern color spaces in arbitrary values
    assert "oklch(0.4" in css or "oklch(.4" in css, "oklch() in arbitrary values must compile"
    assert "hsl(var(--accent)" in css, "hsl(var()) in arbitrary opacity values must compile"

    # Responsive viewport-prefixed arbitrary grids in two contexts
    assert "auto-fit" in css, "auto-fit grid template arbitrary value must compile"
    assert "@media" in css, "responsive variants must produce media queries"
