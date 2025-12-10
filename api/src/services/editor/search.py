"""
File content search for browser-based code editor.
Provides fast full-text search with regex support.
Platform admin resource - no org scoping.
"""

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List

from src.models import SearchRequest, SearchResponse, SearchResult
from src.services.editor.file_operations import get_base_path, validate_and_resolve_path

# Binary file extensions to skip
BINARY_EXTENSIONS = {
    '.pyc', '.pyo', '.so', '.dll', '.dylib', '.exe', '.bin',
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico', '.svg',
    '.mp3', '.mp4', '.avi', '.mov', '.wav', '.flac',
    '.zip', '.tar', '.gz', '.bz2', '.7z', '.rar',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.woff', '.woff2', '.ttf', '.eot', '.otf'
}

# Maximum file size to search (10MB)
MAX_FILE_SIZE = 10 * 1024 * 1024


def should_search_file(file_path: Path) -> bool:
    """
    Determine if file should be searched.

    Args:
        file_path: Path to file

    Returns:
        True if file should be searched, False otherwise
    """
    # Skip if not a file
    if not file_path.is_file():
        return False

    # Skip binary extensions
    if file_path.suffix.lower() in BINARY_EXTENSIONS:
        return False

    # Skip hidden files
    if file_path.name.startswith('.'):
        return False

    # Skip large files
    try:
        if file_path.stat().st_size > MAX_FILE_SIZE:
            return False
    except (PermissionError, OSError):
        return False

    return True


def search_file(
    file_path: Path,
    query: str,
    case_sensitive: bool,
    is_regex: bool,
    base_path: Path
) -> List[SearchResult]:
    """
    Search a single file for matches.

    Args:
        file_path: Path to file to search
        query: Search query (text or regex pattern)
        case_sensitive: Whether to match case-sensitively
        is_regex: Whether query is a regex pattern
        base_path: Base path for relative path calculation

    Returns:
        List of SearchResult objects for this file
    """
    results: List[SearchResult] = []

    try:
        # Read file content
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        # Build regex pattern
        if is_regex:
            pattern = query
        else:
            # Escape special regex characters for literal search
            pattern = re.escape(query)

        # Compile regex with appropriate flags
        flags = 0 if case_sensitive else re.IGNORECASE
        regex = re.compile(pattern, flags)

        # Calculate relative path
        try:
            relative_path = str(file_path.resolve().relative_to(base_path.resolve()))
        except ValueError:
            # File is outside base path, use absolute path
            relative_path = str(file_path)

        # Search each line
        for line_num, line in enumerate(lines, start=1):
            # Remove newline for matching
            line_content = line.rstrip('\n\r')

            # Find all matches in this line
            for match in regex.finditer(line_content):
                # Get context lines (previous and next)
                context_before = None
                context_after = None

                if line_num > 1:
                    context_before = lines[line_num - 2].rstrip('\n\r')

                if line_num < len(lines):
                    context_after = lines[line_num].rstrip('\n\r')

                results.append(SearchResult(
                    file_path=relative_path,
                    line=line_num,
                    column=match.start(),
                    match_text=line_content,
                    context_before=context_before,
                    context_after=context_after
                ))

    except (UnicodeDecodeError, PermissionError, OSError):
        # Skip files that can't be read
        pass

    return results


def collect_files(root_path: Path, file_pattern: str) -> List[Path]:
    """
    Collect all files matching the pattern.

    Args:
        root_path: Root directory to search
        file_pattern: Glob pattern for files (e.g., "**/*.py")

    Returns:
        List of file paths to search
    """
    files_to_search: List[Path] = []

    try:
        # Use glob to find matching files
        for file_path in root_path.glob(file_pattern):
            if should_search_file(file_path):
                files_to_search.append(file_path)
    except (PermissionError, OSError):
        # Skip directories we can't access
        pass

    return files_to_search


def search_files(request: SearchRequest, root_path: str = "") -> SearchResponse:
    """
    Search files for content matching the query.

    Uses parallel processing to search multiple files simultaneously.

    Args:
        request: SearchRequest with query and options
        root_path: Relative path to search root (empty = /home)

    Returns:
        SearchResponse with results and metadata

    Raises:
        ValueError: If query is invalid regex or root path is invalid
    """
    start_time = time.time()

    # Validate root path
    if root_path:
        search_root = validate_and_resolve_path(root_path)
    else:
        search_root = get_base_path()

    # Validate regex if enabled
    if request.is_regex:
        try:
            flags = 0 if request.case_sensitive else re.IGNORECASE
            re.compile(request.query, flags)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {str(e)}")

    # Collect files to search
    files = collect_files(search_root, request.include_pattern or "**/*")
    files_searched = len(files)

    # Search files in parallel
    all_results: List[SearchResult] = []
    base_path = get_base_path()

    # Use ThreadPoolExecutor for parallel file searching
    max_workers = min(8, len(files)) if len(files) > 0 else 1

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit search tasks
        future_to_file = {
            executor.submit(
                search_file,
                file_path,
                request.query,
                request.case_sensitive,
                request.is_regex,
                base_path
            ): file_path
            for file_path in files
        }

        # Collect results as they complete
        for future in as_completed(future_to_file):
            try:
                file_results = future.result()
                all_results.extend(file_results)

                # Stop if we've hit the max results limit
                if len(all_results) >= request.max_results:
                    # Cancel remaining tasks
                    for f in future_to_file:
                        f.cancel()
                    break
            except Exception:
                # Skip files that error during search
                pass

    # Truncate results if needed
    truncated = len(all_results) > request.max_results
    results = all_results[:request.max_results]

    # Calculate search time
    search_time_ms = int((time.time() - start_time) * 1000)

    return SearchResponse(
        query=request.query,
        total_matches=len(results),
        files_searched=files_searched,
        results=results,
        truncated=truncated,
        search_time_ms=search_time_ms
    )
