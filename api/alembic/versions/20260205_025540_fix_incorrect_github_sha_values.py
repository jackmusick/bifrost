"""fix_incorrect_github_sha_values

Revision ID: cc62b0c9f2ad
Revises: 9b3f4d5e6f7a
Create Date: 2026-02-05 02:55:40.263726+00:00

This migration fixes a bug where file_ops.py and reindex.py were incorrectly
setting github_sha on all file operations. The github_sha column should ONLY
be set by the GitHub sync process when a file is actually pushed to or pulled
from GitHub.

Files that have never been synced to GitHub should have github_sha = NULL.
Files that were synced and then modified locally should retain their github_sha
(that's how we detect changes).

The bug caused files to appear as "conflicts" in the sync dialog when they
should have been shown as "outgoing changes" (to push). This happened because:
1. file_ops.py set github_sha = content_hash on every write
2. reindex.py set github_sha = git_sha on every reindex
3. Sync logic saw: "has github_sha, not in remote" = "deleted on remote" = conflict

Fix: Clear github_sha for files that have never been synced. We identify these as:
- Files where github_sha equals content_hash (the bug's signature)
- AND git_status is not 'synced' (if it were synced, github_sha should be preserved)

We use a more conservative approach: only clear github_sha where the file's
current content_hash matches github_sha AND git_status != 'synced'. This means
the github_sha was set by the bug, not by an actual sync operation.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'cc62b0c9f2ad'
down_revision: Union[str, None] = '9b3f4d5e6f7a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Clear github_sha for files that were affected by the bug.
    # The bug signature: github_sha = content_hash AND git_status != 'synced'
    #
    # If a file was actually synced to GitHub and then modified, github_sha
    # would NOT equal content_hash (content_hash changes on modification).
    # So files where github_sha = content_hash were never actually synced.
    op.execute("""
        UPDATE workspace_files
        SET github_sha = NULL
        WHERE github_sha IS NOT NULL
          AND github_sha = content_hash
          AND git_status::text != 'synced'
    """)


def downgrade() -> None:
    # Cannot restore the incorrect github_sha values, and we wouldn't want to.
    # This is a data fix, not a schema change.
    pass
