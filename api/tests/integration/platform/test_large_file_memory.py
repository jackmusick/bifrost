"""
Integration tests for memory behavior when writing large Python modules.

Tests that memory doesn't accumulate when writing multiple large files
sequentially, which was causing OOM in the scheduler (512Mi limit).
"""

import gc
import tracemalloc
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import FileIndex
from src.services.file_storage import FileStorageService
from tests.fixtures.large_module_generator import generate_large_module


@pytest_asyncio.fixture
async def clean_test_modules(db_session: AsyncSession):
    """Clean up test module files before and after each test."""
    await db_session.execute(
        delete(FileIndex).where(FileIndex.path.like("modules/test_mem_%"))
    )
    await db_session.commit()
    yield
    await db_session.execute(
        delete(FileIndex).where(FileIndex.path.like("modules/test_mem_%"))
    )
    await db_session.commit()


class TestLargeFileMemory:
    """Tests for memory behavior with large Python modules."""

    @pytest.mark.asyncio
    @patch("src.services.file_storage.file_ops.set_module", new_callable=AsyncMock)
    @patch("src.services.file_storage.file_ops.invalidate_module", new_callable=AsyncMock)
    async def test_sequential_writes_memory_bounded(
        self, _mock_invalidate, _mock_set, db_session: AsyncSession, clean_test_modules
    ):
        """
        Test that sequential large file writes don't accumulate memory.

        Writes multiple large modules (simulating halopsa.py, sageintacct.py, etc.)
        and verifies:
        1. Current memory after all writes stays low (memory released via db.expire)
        2. Peak memory stays under the scheduler limit (512MB)
        """
        file_storage = FileStorageService(db_session)

        # Phase 1: Write 3x 4MB modules, check peak and current stay bounded
        content_4mb = generate_large_module(target_size_mb=4.0).encode("utf-8")
        assert len(content_4mb) > 3 * 1024 * 1024

        tracemalloc.start()
        try:
            baseline = tracemalloc.get_traced_memory()[0]

            for name in ["test_mem_1.py", "test_mem_2.py", "test_mem_3.py"]:
                result = await file_storage.write_file(
                    path=f"modules/{name}",
                    content=content_4mb,
                    updated_by="test",
                    force_deactivation=True,
                )
                # file_record is now always None (workspace_files removed)

            current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        growth = current - baseline
        print(f"Phase 1 - baseline={baseline/1024/1024:.1f}MB, "
              f"current={current/1024/1024:.1f}MB, "
              f"peak={peak/1024/1024:.1f}MB, "
              f"growth={growth/1024/1024:.1f}MB")

        # Without the OOM fix, 3x 4MB files with AST parsing would use 300MB+.
        # With the fix, current memory stays bounded. Dual-write to file_index
        # adds ~12MB overhead, so threshold is 75MB (still 7x under 512MB limit).
        assert current < 75 * 1024 * 1024, f"Memory not released: {current/1024/1024:.1f}MB"
        assert peak < 450 * 1024 * 1024, f"Peak memory {peak/1024/1024:.1f}MB exceeds 450MB"

        # Phase 2: Write 5x 2MB modules, verify no catastrophic accumulation
        del content_4mb
        gc.collect()

        content_2mb = generate_large_module(target_size_mb=2.0).encode("utf-8")
        num_files = 5
        memory_after_each: list[float] = []

        tracemalloc.start()
        try:
            for i in range(num_files):
                result = await file_storage.write_file(
                    path=f"modules/test_mem_accum_{i}.py",
                    content=content_2mb,
                    updated_by="test",
                    force_deactivation=True,
                )
                # file_record is now always None (workspace_files removed)
                del result
                gc.collect()

                current, _ = tracemalloc.get_traced_memory()
                memory_after_each.append(current / 1024 / 1024)

            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        print(f"Phase 2 - memory per file (MB): {[f'{m:.1f}' for m in memory_after_each]}")
        print(f"Phase 2 - peak={peak/1024/1024:.1f}MB")

        last_file_memory = memory_after_each[-1]

        # Key assertion: total memory stays bounded (not growing to 100s of MB).
        # Note: tracemalloc reports arena-level allocations that may show ~2MB per
        # file due to pymalloc arena fragmentation, even though Python objects are
        # properly freed. The important thing is staying under the 512MB scheduler
        # limit, not achieving zero growth.
        assert last_file_memory < 100, (
            f"Memory too high after {num_files} files: {last_file_memory:.1f}MB. "
            f"Progression: {[f'{m:.1f}' for m in memory_after_each]}"
        )
        assert peak / 1024 / 1024 < 100, (
            f"Peak memory too high: {peak/1024/1024:.1f}MB"
        )
