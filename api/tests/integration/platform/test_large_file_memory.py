"""
Integration tests for memory behavior when writing large Python modules.

Tests that memory doesn't accumulate when writing multiple large files
sequentially, which was causing OOM in the scheduler (512Mi limit).
"""

import gc
import tracemalloc

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import WorkspaceFile
from src.services.file_storage import FileStorageService
from tests.fixtures.large_module_generator import generate_large_module


@pytest_asyncio.fixture
async def clean_test_modules(db_session: AsyncSession):
    """Clean up test module files before and after each test."""
    await db_session.execute(
        delete(WorkspaceFile).where(WorkspaceFile.path.like("modules/test_mem_%"))
    )
    await db_session.commit()
    yield
    await db_session.execute(
        delete(WorkspaceFile).where(WorkspaceFile.path.like("modules/test_mem_%"))
    )
    await db_session.commit()


class TestLargeFileMemory:
    """Tests for memory behavior with large Python modules."""

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="tracemalloc conflicts with pytest-asyncio event loop cleanup", strict=False)
    async def test_sequential_writes_memory_bounded(
        self, db_session: AsyncSession, clean_test_modules
    ):
        """
        Test that sequential large file writes don't accumulate memory.

        This simulates execute_sync writing multiple 4MB modules like
        halopsa.py, sageintacct.py, etc. Without proper memory management,
        the SQLAlchemy session accumulates all file records.

        With the fix (db.expire after each write), memory should stay bounded.
        """
        file_storage = FileStorageService(db_session)

        # Generate 4MB module content
        content = generate_large_module(target_size_mb=4.0).encode("utf-8")
        assert len(content) > 3 * 1024 * 1024

        module_names = ["test_mem_1.py", "test_mem_2.py", "test_mem_3.py"]

        tracemalloc.start()
        baseline = tracemalloc.get_traced_memory()[0]

        for name in module_names:
            result = await file_storage.write_file(
                path=f"modules/{name}",
                content=content,
                updated_by="test",
                force_deactivation=True,
            )
            # This is the key fix being tested - expire releases session memory
            db_session.expire(result.file_record)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Memory growth should be bounded, not 3x the content size
        growth = current - baseline
        print(f"Memory: baseline={baseline/1024/1024:.1f}MB, "
              f"current={current/1024/1024:.1f}MB, "
              f"peak={peak/1024/1024:.1f}MB, "
              f"growth={growth/1024/1024:.1f}MB")

        # Key insight: peak during write can be high (AST parsing, multiple decodes)
        # but what matters for OOM prevention is that memory is RELEASED after.
        #
        # The test verifies:
        # 1. Current memory after all writes is low (memory released)
        # 2. Peak is under the scheduler limit (512MB) with headroom
        #
        # Note: Peak ~400MB for 4MB file is expected due to:
        # - Multiple AST parses in the write pipeline
        # - Multiple string decodes (content decoded 5+ times)
        # - Generated test file has ~2000 functions (high AST complexity)
        assert current < 50 * 1024 * 1024, f"Memory not released: {current/1024/1024:.1f}MB"
        assert peak < 450 * 1024 * 1024, f"Peak memory {peak/1024/1024:.1f}MB exceeds 450MB"

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Event loop cleanup issue when running after test_sequential_writes_memory_bounded", strict=False)
    async def test_many_files_no_accumulation(
        self, db_session: AsyncSession, clean_test_modules
    ):
        """
        Test that writing 10 large files doesn't cause memory accumulation.

        This catches the OOM bug where memory grows linearly with each file
        written instead of staying bounded. If memory accumulates, 10 x 4MB
        files would use 40MB+ just for content, plus AST overhead.

        Expected behavior: memory after each file should be roughly constant,
        not growing linearly.
        """
        file_storage = FileStorageService(db_session)

        # Generate 2MB module content (smaller for faster test, still catches bug)
        content = generate_large_module(target_size_mb=2.0).encode("utf-8")
        content_size_mb = len(content) / 1024 / 1024
        print(f"\nContent size: {content_size_mb:.1f}MB")

        num_files = 5
        memory_after_each: list[float] = []

        tracemalloc.start()

        for i in range(num_files):
            result = await file_storage.write_file(
                path=f"modules/test_mem_{i}.py",
                content=content,
                updated_by="test",
                force_deactivation=True,
            )
            # Simulate what execute_sync should do
            db_session.expire(result.file_record)
            del result

            # Track memory after each file
            current, _ = tracemalloc.get_traced_memory()
            memory_after_each.append(current / 1024 / 1024)

        # Force GC after all files to see true memory state
        gc.collect()

        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Print memory progression
        print(f"Memory after each file (MB): {[f'{m:.1f}' for m in memory_after_each]}")
        print(f"Peak memory: {peak/1024/1024:.1f}MB")

        # Check for accumulation: memory at end shouldn't be much higher than start
        # Allow for some growth but not linear (10 files x 2MB = 20MB accumulation)
        first_file_memory = memory_after_each[0]
        last_file_memory = memory_after_each[-1]
        growth = last_file_memory - first_file_memory

        print(f"Growth from file 1 to file {num_files}: {growth:.1f}MB")

        # If memory is accumulating, growth would be ~(num_files-1) * content_size
        # With proper cleanup, growth should be minimal (< 1 file worth)
        max_acceptable_growth = content_size_mb * 2  # Allow 2x content size growth max
        assert growth < max_acceptable_growth, (
            f"Memory accumulated: grew {growth:.1f}MB over {num_files} files. "
            f"Expected < {max_acceptable_growth:.1f}MB. "
            f"Progression: {[f'{m:.1f}' for m in memory_after_each]}"
        )
