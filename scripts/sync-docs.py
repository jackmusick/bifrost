#!/usr/bin/env python3
"""
Sync Bifrost documentation from bifrost-docs project.

Copies MDX files, strips MDX syntax while preserving code blocks,
and writes plain text files for API bundling.

Usage:
    python scripts/sync-docs.py

Prerequisites:
    - bifrost-docs repo cloned alongside bifrost-api
"""

import re
import shutil
import sys
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).parent
API_DIR = SCRIPT_DIR.parent / "api"
DOCS_SOURCE = Path.home() / "GitHub" / "bifrost-docs" / "src" / "content" / "docs"
# Output to shared/ which is already mounted in Docker as /app/shared
DOCS_TARGET = API_DIR / "shared" / "docs"


def parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """Extract frontmatter and return (metadata, body)."""
    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    frontmatter: dict[str, str] = {}
    for line in parts[1].strip().split("\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            # Strip quotes and whitespace
            frontmatter[key.strip()] = value.strip().strip("\"'")

    return frontmatter, parts[2]


def strip_mdx_syntax(content: str) -> str:
    """Remove MDX-specific syntax while preserving code blocks."""
    # Preserve code blocks by replacing temporarily with lowercase placeholders
    # (JSX component stripping only matches uppercase component names)
    code_blocks: list[str] = []

    def save_code_block(match: re.Match[str]) -> str:
        code_blocks.append(match.group(0))
        return f"__codeblock_{len(code_blocks) - 1}__"

    content = re.sub(r"```[\s\S]*?```", save_code_block, content)

    # Strip import statements (single and multi-line)
    content = re.sub(r"^import\s+.*?[;\n]", "", content, flags=re.MULTILINE)

    # Strip JSX component tags (but keep inner content)
    # These only match uppercase component names like <Steps>, <Aside>, etc.
    # Self-closing tags: <Component ... />
    content = re.sub(r"<[A-Z][a-zA-Z]*[^>]*/\s*>", "", content)
    # Opening tags: <Component ...>
    content = re.sub(r"<[A-Z][a-zA-Z]*[^>]*>", "", content)
    # Closing tags: </Component>
    content = re.sub(r"</[A-Z][a-zA-Z]*>", "", content)

    # Strip image references
    content = re.sub(r"!\[.*?\]\([^)]+\)", "", content)

    # Strip link-only references that just show the URL (common in docs)
    # But keep inline links with text like [text](url)

    # Restore code blocks
    for i, block in enumerate(code_blocks):
        content = content.replace(f"__codeblock_{i}__", block)

    # Clean up excessive whitespace
    content = re.sub(r"\n{3,}", "\n\n", content)

    return content.strip()


def process_mdx_file(source_path: Path, target_path: Path) -> None:
    """Process a single MDX file."""
    content = source_path.read_text(encoding="utf-8")

    # Parse frontmatter
    metadata, body = parse_frontmatter(content)

    # Strip MDX syntax
    processed = strip_mdx_syntax(body)

    # Build output with title and description
    output_lines: list[str] = []
    if title := metadata.get("title"):
        output_lines.append(f"# {title}")
    if description := metadata.get("description"):
        output_lines.append(f"\n{description}")
    if output_lines:
        output_lines.append("\n---\n")
    output_lines.append(processed)

    output = "\n".join(output_lines)

    # Write to target
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(output, encoding="utf-8")


def main() -> int:
    """Main sync function."""
    if not DOCS_SOURCE.exists():
        print(f"Error: Source docs not found at {DOCS_SOURCE}")
        print("Make sure bifrost-docs is cloned alongside bifrost-api")
        return 1

    # Clear target directory
    if DOCS_TARGET.exists():
        shutil.rmtree(DOCS_TARGET)
    DOCS_TARGET.mkdir(parents=True)

    # Process all MDX files
    mdx_files = list(DOCS_SOURCE.rglob("*.mdx"))
    # Also include .md files (like index.md)
    mdx_files.extend(DOCS_SOURCE.rglob("*.md"))

    print(f"Processing {len(mdx_files)} documentation files...")

    for source_file in sorted(mdx_files):
        relative = source_file.relative_to(DOCS_SOURCE)
        # Change extension to .txt
        target_file = DOCS_TARGET / relative.with_suffix(".txt")
        process_mdx_file(source_file, target_file)
        print(f"  {relative}")

    print(f"\nDone! Processed {len(mdx_files)} files to {DOCS_TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
