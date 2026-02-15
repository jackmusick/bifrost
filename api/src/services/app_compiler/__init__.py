"""
Server-side TSX/JSX compiler for Bifrost app files.

Uses a Node.js subprocess running @babel/standalone to compile
app source files. This is the same Babel pipeline used by the
client (client/src/lib/app-code-compiler.ts), ported to run
server-side so _apps/ always contains compiled JS.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

COMPILE_SCRIPT = Path(__file__).parent / "compile.js"


@dataclass
class CompileResult:
    """Result of compiling a single file."""
    path: str
    success: bool
    compiled: str | None = None
    error: str | None = None
    default_export: str | None = None
    named_exports: list[str] = field(default_factory=list)


class AppCompilerService:
    """Compile TSX/JSX source files via Node.js subprocess."""

    async def compile_file(self, source: str, path: str = "component.tsx") -> CompileResult:
        """Compile a single file."""
        results = await self.compile_batch([{"path": path, "source": source}])
        return results[0]

    async def compile_batch(self, files: list[dict]) -> list[CompileResult]:
        """Compile multiple files in a single Node.js invocation."""
        if not files:
            return []

        input_data = json.dumps({"files": files})

        try:
            proc = await asyncio.create_subprocess_exec(
                "node", str(COMPILE_SCRIPT),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate(input=input_data.encode())

            if proc.returncode != 0:
                error_msg = stderr.decode().strip() or "Node process exited with error"
                logger.error(f"Compiler process failed: {error_msg}")
                return [
                    CompileResult(path=f["path"], success=False, error=error_msg)
                    for f in files
                ]

            output = json.loads(stdout.decode())

            if "error" in output:
                return [
                    CompileResult(path=f["path"], success=False, error=output["error"])
                    for f in files
                ]

            results = []
            for item in output.get("results", []):
                if item.get("error"):
                    results.append(CompileResult(
                        path=item["path"],
                        success=False,
                        error=item["error"],
                    ))
                else:
                    results.append(CompileResult(
                        path=item["path"],
                        success=True,
                        compiled=item["compiled"],
                        default_export=item.get("defaultExport"),
                        named_exports=item.get("namedExports", []),
                    ))
            return results

        except FileNotFoundError:
            logger.error("Node.js not found — cannot compile app files")
            return [
                CompileResult(path=f["path"], success=False, error="Node.js not available")
                for f in files
            ]
        except Exception as e:
            logger.exception(f"Compilation failed: {e}")
            return [
                CompileResult(path=f["path"], success=False, error=str(e))
                for f in files
            ]
