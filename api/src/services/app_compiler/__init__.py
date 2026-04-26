"""
Server-side TSX/JSX compiler and Tailwind CSS generator for Bifrost app files.

Uses Node.js subprocesses:
- @babel/standalone to compile app source files (same pipeline as client)
- @tailwindcss/node to generate per-app Tailwind CSS from class candidates
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

COMPILE_SCRIPT = Path(__file__).parent / "compile.js"
TAILWIND_SCRIPT = Path(__file__).parent / "tailwind.js"


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


# Extract all string literals from compiled JS output, then split into tokens.
# Over-extraction is fine — Tailwind silently ignores unknown candidates.
# This is intentionally broad to handle both JSX (className="...") and compiled
# output (className: "...") without fragile pattern matching.
_STRING_LITERAL = re.compile(r'"([^"]{1,500})"')
_TOKEN_SPLIT = re.compile(r"[\s,]+")
# Tailwind classes contain hyphens, brackets, colons, or slashes.
# Single-word utilities (flex, grid, hidden, etc.) also need to pass through.
_LOOKS_LIKE_CLASS = re.compile(
    r"^!?-?[a-z][a-z0-9:\-/\[.=#%_*>~&+\]]*$",
    re.IGNORECASE,
)


class AppTailwindService:
    """Generate Tailwind CSS for app source files via @tailwindcss/node."""

    @staticmethod
    def extract_candidates(sources: list[str]) -> list[str]:
        """Extract Tailwind class candidates from source strings.

        Scans all string literals and splits into whitespace-separated tokens.
        Over-extraction is harmless — Tailwind ignores unknown candidates.
        """
        candidates: set[str] = set()
        for source in sources:
            for match in _STRING_LITERAL.finditer(source):
                for token in _TOKEN_SPLIT.split(match.group(1)):
                    token = token.strip()
                    if token and _LOOKS_LIKE_CLASS.match(token):
                        candidates.add(token)
        return sorted(candidates)

    @staticmethod
    async def generate_css(sources: list[str]) -> str | None:
        """Extract candidates from sources and generate Tailwind CSS.

        Returns the generated CSS string, or None on failure.
        """
        candidates = AppTailwindService.extract_candidates(sources)
        if not candidates:
            return None

        input_data = json.dumps({"candidates": candidates})

        try:
            proc = await asyncio.create_subprocess_exec(
                "node", str(TAILWIND_SCRIPT),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate(input=input_data.encode())

            if proc.returncode != 0:
                error_msg = stderr.decode().strip() or "tailwind.js exited with error"
                logger.error(f"Tailwind CSS generation failed: {error_msg}")
                return None

            output = json.loads(stdout.decode())
            if output.get("error"):
                logger.error(f"Tailwind CSS generation error: {output['error']}")
                return None

            css = output.get("css", "")
            return css if css else None

        except FileNotFoundError:
            logger.error("Node.js not found — cannot generate Tailwind CSS")
            return None
        except Exception as e:
            logger.exception(f"Tailwind CSS generation failed: {e}")
            return None
