"""
Git Sync Service

GitPython-based synchronization. S3 _repo/ is the persistent working tree.

Key principles:
1. Git working tree is source of truth during sync operations
2. GitPython for clone/pull/push/commit
3. Conflict detection with user resolution
4. .bifrost/ split manifest files declare entity identity
5. Preflight validates repo health (syntax, lint, refs, orphans)
"""

import hashlib
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

import yaml
from git import Repo as GitRepo
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import Settings, get_settings
from src.models.contracts.github import (
    PreflightIssue,
    PreflightResult,
)
from src.services.git_repo_manager import GitRepoManager
from src.services.github_sync_entity_metadata import extract_entity_metadata

if TYPE_CHECKING:
    from src.models.contracts.github import (
        AbortMergeResult,
        CommitResult,
        DiscardResult,
        DiffResult,
        FetchResult,
        PullResult,
        PushResult,
        ResolveResult,
        SyncResult,
        WorkingTreeStatus,
    )
    from src.services.repo_storage import RepoStorage
    from src.services.sync_ops import SyncOp

from src.services.manifest import (
    Manifest,
    get_all_entity_ids,
    read_manifest_from_dir,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Errors
# =============================================================================


class SyncError(Exception):
    """Error during sync operation."""
    pass


# =============================================================================
# Helpers
# =============================================================================


def _content_hash(content: bytes) -> str:
    """SHA-256 of bytes."""
    return hashlib.sha256(content).hexdigest()


def _walk_tree(root: Path) -> dict[str, bytes]:
    """Walk a directory tree and return {relative_path: content} for all files."""
    files: dict[str, bytes] = {}
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        rel = str(p.relative_to(root))
        # Skip .git internals
        if rel.startswith(".git/") or rel == ".git":
            continue
        files[rel] = p.read_bytes()
    return files


def _three_way_merge_dicts(
    base: dict, ours: dict, theirs: dict
) -> dict:
    """3-way merge two dicts against a common base.

    - Keys deleted by either side (present in base but absent in ours/theirs)
      stay deleted unless the other side modified the value.
    - Keys added by either side are included.
    - When both sides modify the same key, theirs wins.
    """
    merged = {}
    # Preserve key ordering: ours first, then theirs additions, then base-only
    seen: set = set()
    ordered_keys: list = []
    for key in ours:
        if key not in seen:
            ordered_keys.append(key)
            seen.add(key)
    for key in theirs:
        if key not in seen:
            ordered_keys.append(key)
            seen.add(key)
    for key in base:
        if key not in seen:
            ordered_keys.append(key)
            seen.add(key)

    for key in ordered_keys:
        in_base = key in base
        in_ours = key in ours
        in_theirs = key in theirs

        if in_ours and in_theirs:
            # Both have it — if both are dicts, recurse; otherwise theirs wins
            if isinstance(ours[key], dict) and isinstance(theirs[key], dict):
                base_val = base.get(key, {}) if isinstance(base.get(key), dict) else {}
                merged[key] = _three_way_merge_dicts(base_val, ours[key], theirs[key])
            else:
                merged[key] = theirs[key]
        elif in_ours and not in_theirs:
            if in_base:
                # Theirs deleted it — honor the deletion unless ours modified it
                if base.get(key) != ours[key]:
                    merged[key] = ours[key]  # Ours modified, keep it
                # else: theirs deleted, ours unchanged → delete
            else:
                merged[key] = ours[key]  # Added by ours
        elif in_theirs and not in_ours:
            if in_base:
                # Ours deleted it — honor the deletion unless theirs modified it
                if base.get(key) != theirs[key]:
                    merged[key] = theirs[key]  # Theirs modified, keep it
                # else: ours deleted, theirs unchanged → delete
            else:
                merged[key] = theirs[key]  # Added by theirs
        # else: neither has it (shouldn't happen since key came from one of them)

    return merged


def _auto_resolve_manifest_conflicts(repo: GitRepo, work_dir: Path, unmerged: dict) -> set[str]:
    """Auto-resolve .bifrost/*.yaml manifest conflicts via 3-way YAML merge.

    For each conflicted manifest file:
    1. Parse base (stage 1), ours (stage 2), and theirs (stage 3) YAML
    2. 3-way merge respecting additions and deletions from both sides
    3. Write merged YAML to working tree and git add
    4. On failure, accept theirs entirely

    Returns set of paths that were auto-resolved (removed from conflict list).
    """
    resolved_paths: set[str] = set()

    for cpath in list(unmerged.keys()):
        cpath_str = str(cpath)
        if not (cpath_str.startswith(".bifrost/") and cpath_str.endswith(".yaml")):
            continue

        try:
            # Parse all three sides (base, ours, theirs)
            base_yaml: dict = {}
            ours_yaml: dict = {}
            theirs_yaml: dict = {}
            try:
                base_raw = repo.git.show(f":1:{cpath_str}")
                base_yaml = yaml.safe_load(base_raw) or {}
            except Exception:
                base_yaml = {}
            try:
                ours_raw = repo.git.show(f":2:{cpath_str}")
                ours_yaml = yaml.safe_load(ours_raw) or {}
            except Exception:
                ours_yaml = {}
            try:
                theirs_raw = repo.git.show(f":3:{cpath_str}")
                theirs_yaml = yaml.safe_load(theirs_raw) or {}
            except Exception:
                theirs_yaml = {}

            if not isinstance(ours_yaml, dict) or not isinstance(theirs_yaml, dict):
                # Not a dict-shaped YAML — fall back to accepting theirs
                raise ValueError("Non-dict YAML")
            if not isinstance(base_yaml, dict):
                base_yaml = {}

            # 3-way merge respecting deletions
            merged = _three_way_merge_dicts(base_yaml, ours_yaml, theirs_yaml)

            # Write merged YAML
            merged_yaml = yaml.dump(merged, default_flow_style=False, sort_keys=True, allow_unicode=True)
            file_path = work_dir / cpath_str
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(merged_yaml)
            repo.git.add(cpath_str)
            resolved_paths.add(cpath_str)
            logger.info(f"Auto-resolved manifest conflict: {cpath_str}")

        except Exception as e:
            # Fall back to accepting theirs entirely
            logger.warning(f"Manifest auto-merge failed for {cpath_str}, accepting theirs: {e}")
            try:
                theirs_raw = repo.git.show(f":3:{cpath_str}")
                file_path = work_dir / cpath_str
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(theirs_raw)
                repo.git.add(cpath_str)
                resolved_paths.add(cpath_str)
            except Exception as fallback_err:
                logger.error(f"Failed to accept theirs for {cpath_str}: {fallback_err}")

    return resolved_paths


def _classify_conflict_type(unmerged: dict, cpath: str) -> str:
    """Classify conflict type from git unmerged blob stages.

    Stage 1 = common ancestor, Stage 2 = ours, Stage 3 = theirs.
    """
    # unmerged keys may be PathLike — find matching entry by str comparison
    entries = None
    for key, val in unmerged.items():
        if str(key) == cpath:
            entries = val
            break
    if not entries:
        return "both_modified"
    stages = {stage for stage, _blob in entries}
    if stages >= {1, 2, 3}:
        return "both_modified"
    elif stages == {2, 3}:
        return "both_added"
    elif stages == {1, 3}:
        return "deleted_by_us"
    elif stages == {1, 2}:
        return "deleted_by_them"
    else:
        return "both_modified"


# =============================================================================
# Manifest diff (pure in-memory comparison)
# =============================================================================


def _diff_manifests(incoming: "Manifest", current: "Manifest") -> list[dict[str, str]]:
    """Compare two Manifest objects and return entity-level changes.

    Returns list of dicts with keys: action, entity_type, name, organization.
    Only changed entities are included (unchanged are omitted).
    """
    # Build org ID → name lookup from both manifests
    org_lookup: dict[str, str] = {}
    for org in incoming.organizations:
        org_lookup[org.id] = org.name
    for org in current.organizations:
        org_lookup.setdefault(org.id, org.name)

    # Build integration ID → name lookup for config display
    integ_lookup: dict[str, str] = {}
    for integ in incoming.integrations.values():
        integ_lookup[integ.id] = integ.name
    for integ in current.integrations.values():
        integ_lookup.setdefault(integ.id, integ.name)

    def _resolve_org(entity: object) -> str:
        oid = getattr(entity, "organization_id", None)
        if not oid:
            return "Global"
        return org_lookup.get(oid, oid) or "Global"

    changes: list[dict[str, str]] = []

    # -- List-based entities (organizations, roles) --
    _diff_list_entities(
        incoming.organizations, current.organizations,
        "organizations", org_lookup, changes,
    )
    _diff_list_entities(
        incoming.roles, current.roles,
        "roles", org_lookup, changes,
    )

    # -- Dict-based entities --
    _DICT_ENTITY_TYPES: list[tuple[str, str]] = [
        ("workflows", "workflows"),
        ("integrations", "integrations"),
        ("configs", "configs"),
        ("tables", "tables"),
        ("events", "events"),
        ("forms", "forms"),
        ("agents", "agents"),
        ("apps", "apps"),
    ]

    for attr, entity_type in _DICT_ENTITY_TYPES:
        incoming_dict: dict = getattr(incoming, attr)
        current_dict: dict = getattr(current, attr)

        # Index by entity .id
        incoming_by_id = {v.id: v for v in incoming_dict.values()}
        current_by_id = {v.id: v for v in current_dict.values()}

        all_ids = set(incoming_by_id) | set(current_by_id)
        for eid in all_ids:
            inc = incoming_by_id.get(eid)
            cur = current_by_id.get(eid)

            if inc and not cur:
                action = "add"
                entity = inc
            elif cur and not inc:
                action = "delete"
                entity = cur
            else:
                assert inc is not None and cur is not None
                # Compare serialized form
                if inc.model_dump(mode="json", by_alias=True) == cur.model_dump(mode="json", by_alias=True):
                    continue  # No change
                action = "update"
                entity = inc

            # Resolve display name
            if entity_type == "configs":
                name = getattr(entity, "key", "") or str(eid)
                iid = getattr(entity, "integration_id", None)
                if iid and iid in integ_lookup:
                    name = f"{integ_lookup[iid]}/{name}"
            else:
                name = getattr(entity, "name", None) or getattr(entity, "function_name", None) or str(eid)

            changes.append({
                "action": action,
                "entity_type": entity_type,
                "name": name,
                "organization": _resolve_org(entity),
            })

    # Sort: entity_type, then action priority (add > update > delete), then name
    _ACTION_ORDER = {"add": 0, "update": 1, "delete": 2, "keep": 3}
    changes.sort(key=lambda c: (c["entity_type"], _ACTION_ORDER.get(c["action"], 9), c["name"]))

    return changes


def _diff_list_entities(
    incoming_list: list,
    current_list: list,
    entity_type: str,
    org_lookup: dict[str, str],
    changes: list[dict[str, str]],
) -> None:
    """Diff list-based manifest entities (organizations, roles)."""
    incoming_by_id = {e.id: e for e in incoming_list}
    current_by_id = {e.id: e for e in current_list}

    for eid in set(incoming_by_id) | set(current_by_id):
        inc = incoming_by_id.get(eid)
        cur = current_by_id.get(eid)

        if inc and not cur:
            action = "add"
            entity = inc
        elif cur and not inc:
            action = "delete"
            entity = cur
        else:
            assert inc is not None and cur is not None
            if inc.model_dump(mode="json", by_alias=True) == cur.model_dump(mode="json", by_alias=True):
                continue
            action = "update"
            entity = inc

        oid = getattr(entity, "organization_id", None)
        org = (org_lookup.get(oid, oid) or "Global") if oid else "Global"

        changes.append({
            "action": action,
            "entity_type": entity_type,
            "name": getattr(entity, "name", "") or str(eid),
            "organization": org,
        })


# =============================================================================
# Standalone manifest import (no git, reads from S3)
# =============================================================================

@dataclass
class ManifestImportResult:
    """Result of importing manifest from repo."""
    applied: bool = False
    dry_run: bool = False
    warnings: list[str] = field(default_factory=list)
    manifest_files: dict[str, str] = field(default_factory=dict)
    modified_files: dict[str, str] = field(default_factory=dict)
    deleted_entities: list[str] = field(default_factory=list)
    entity_changes: list[dict[str, str]] = field(default_factory=list)


async def import_manifest_from_repo(
    db: AsyncSession,
    delete_removed_entities: bool = False,
    dry_run: bool = False,
) -> ManifestImportResult:
    """Import manifest from S3 _repo/.bifrost/ into DB.

    Standalone function (not a method on GitHubSyncService) that:
    1. Reads .bifrost/*.yaml from S3 via RepoStorage
    2. Parses with parse_manifest_dir()
    3. Validates with validate_manifest()
    4. Resolves entities to DB using GitHubSyncService.plan_import
    5. Runs indexer side-effects for forms/agents
    6. Regenerates manifest from DB
    7. Returns ManifestImportResult
    """
    from src.services.repo_storage import RepoStorage
    from src.services.manifest import (
        MANIFEST_FILES,
        parse_manifest_dir,
        serialize_manifest_dir,
        validate_manifest,
    )
    from src.services.manifest_generator import generate_manifest

    result = ManifestImportResult()
    repo = RepoStorage()

    # 1. Read .bifrost/*.yaml from S3
    manifest_yaml_files: dict[str, str] = {}
    for _entity_type, filename in MANIFEST_FILES.items():
        s3_path = f".bifrost/{filename}"
        try:
            content = await repo.read(s3_path)
            manifest_yaml_files[filename] = content.decode("utf-8")
        except Exception:
            pass  # File doesn't exist in S3, skip

    if not manifest_yaml_files:
        result.warnings.append("No .bifrost/ manifest files found in repo")
        return result

    # 2. Parse
    try:
        manifest = parse_manifest_dir(manifest_yaml_files)
    except Exception as e:
        result.warnings.append(f"Failed to parse manifest: {e}")
        return result

    # 3. Validate
    validation_errors = validate_manifest(manifest)
    if validation_errors:
        result.warnings.extend(validation_errors)
        return result

    # 4. Dry-run: pure manifest comparison (no DB writes)
    if dry_run:
        db_manifest = await generate_manifest(db)
        result.entity_changes = _diff_manifests(manifest, db_manifest)
        result.dry_run = True
        return result

    # Helper: read a file from S3, returning None on failure
    async def _read_or_none(path: str) -> bytes | None:
        try:
            return await repo.read(path)
        except Exception:
            return None

    # 5. Run entity resolution via direct S3 reads (no temp dir needed)
    service = GitHubSyncService(db, repo_url="", branch="main")

    try:
        async with db.begin_nested():
            all_ops = await service.plan_import(manifest, repo=repo, dry_run=False)

            # Build entity_changes from upsert ops
            from src.services.sync_ops import Upsert as UpsertOp
            for op in all_ops:
                if isinstance(op, UpsertOp) and op.action_taken:
                    result.entity_changes.append({
                        "action": "add" if op.action_taken == "inserted" else "update",
                        "entity_type": getattr(op.model, "__tablename__", "unknown"),
                        "name": op.values.get("name") or op.values.get("function_name") or op.values.get("key") or str(op.id),
                    })

            # Run indexer side-effects (same as _import_all_entities)
            from src.services.file_storage.indexers.form import FormIndexer
            form_indexer = FormIndexer(db)
            for _form_name, mform in manifest.forms.items():
                content_bytes = await _read_or_none(mform.path)
                if content_bytes is None:
                    continue
                original_data = yaml.safe_load(content_bytes.decode("utf-8"))
                if original_data:
                    data = dict(original_data)
                    data["id"] = mform.id
                    await service._resolve_ref_field(data, "workflow_id")
                    await service._resolve_ref_field(data, "launch_workflow_id")
                    updated_content = (yaml.dump(data, default_flow_style=False, sort_keys=True).rstrip() + "\n").encode("utf-8")
                    await form_indexer.index_form(f"forms/{mform.id}.form.yaml", updated_content)

                    # Only mark as modified if data actually changed (not just formatting)
                    if data != original_data:
                        result.modified_files[mform.path] = updated_content.decode("utf-8")

                    # Post-indexer: update org_id and access_level
                    from sqlalchemy import update as sa_update
                    from src.models.orm.forms import Form
                    org_id_uuid = UUID(mform.organization_id) if mform.organization_id else None
                    form_id_uuid = UUID(mform.id)
                    post_values: dict = {}
                    if org_id_uuid:
                        post_values["organization_id"] = org_id_uuid
                    if mform.access_level:
                        post_values["access_level"] = mform.access_level
                    if post_values:
                        post_values["updated_at"] = datetime.now(timezone.utc)
                        await db.execute(
                            sa_update(Form).where(Form.id == form_id_uuid).values(**post_values)
                        )

            from src.services.file_storage.indexers.agent import AgentIndexer
            agent_indexer = AgentIndexer(db)
            for _agent_name, magent in manifest.agents.items():
                content_bytes = await _read_or_none(magent.path)
                if content_bytes is None:
                    continue
                original_data = yaml.safe_load(content_bytes.decode("utf-8"))
                if original_data:
                    data = dict(original_data)
                    data["id"] = magent.id
                    await service._resolve_ref_field(data, "tool_ids")
                    if "tools" in data and "tool_ids" not in data:
                        await service._resolve_ref_field(data, "tools")
                    updated_content = (yaml.dump(data, default_flow_style=False, sort_keys=True).rstrip() + "\n").encode("utf-8")
                    await agent_indexer.index_agent(f"agents/{magent.id}.agent.yaml", updated_content)

                    # Only mark as modified if data actually changed (not just formatting)
                    if data != original_data:
                        result.modified_files[magent.path] = updated_content.decode("utf-8")

                    # Post-indexer: update org_id and access_level
                    from sqlalchemy import update as sa_update
                    from src.models.orm.agents import Agent
                    org_id_uuid = UUID(magent.organization_id) if magent.organization_id else None
                    agent_id_uuid = UUID(magent.id)
                    post_values_a: dict = {}
                    if org_id_uuid:
                        post_values_a["organization_id"] = org_id_uuid
                    if magent.access_level:
                        post_values_a["access_level"] = magent.access_level
                    if post_values_a:
                        post_values_a["updated_at"] = datetime.now(timezone.utc)
                        await db.execute(
                            sa_update(Agent).where(Agent.id == agent_id_uuid).values(**post_values_a)
                        )

            # Run entity deletions if requested
            if delete_removed_entities:
                deletion_changes = await service._resolve_deletions(
                    manifest=manifest, repo=repo, dry_run=False,
                )
                for ec in deletion_changes:
                    result.deleted_entities.append(
                        f"{ec.entity_type}: {ec.name}"
                    )
                    result.entity_changes.append({
                        "action": "delete" if ec.action == "removed" else ec.action,
                        "entity_type": ec.entity_type,
                        "name": ec.name,
                    })

            result.applied = True

    except Exception as e:
        result.warnings.append(f"Entity resolution failed: {e}")
        logger.warning(f"Manifest import entity resolution failed: {e}", exc_info=True)

    # 7. Regenerate manifest from DB
    try:
        new_manifest = await generate_manifest(db)
        result.manifest_files = serialize_manifest_dir(new_manifest)
    except Exception as e:
        result.warnings.append(f"Manifest regeneration failed: {e}")

    return result


# =============================================================================
# Git Sync Service
# =============================================================================


class GitHubSyncService:
    """
    Git sync service using GitPython.

    All git operations go through GitPython against repo_url.
    The working tree is serialized to/from S3 _repo/ between operations.
    """

    def __init__(
        self,
        db: AsyncSession,
        repo_url: str,
        branch: str = "main",
        settings: Settings | None = None,
    ):
        self.db = db
        self.repo_url = repo_url
        self.branch = branch
        self.repo_manager = GitRepoManager(settings or get_settings())

    # -----------------------------------------------------------------
    # Preflight: validate repo health
    # -----------------------------------------------------------------

    async def preflight(
        self,
    ) -> PreflightResult:
        """
        Validate the remote repo's health without syncing.

        Uses GitRepoManager to restore persistent .git/ from S3.
        Checks: Python syntax, ruff lint, UUID ref resolution, manifest validity.
        """
        async with self.repo_manager.checkout() as work_dir:
            if not (work_dir / ".git").exists():
                self._clone_or_init(work_dir)
            return await self._run_preflight(work_dir)

    # -----------------------------------------------------------------
    # Desktop-style operations: fetch, status, commit, pull, push, resolve, diff
    # -----------------------------------------------------------------

    # -----------------------------------------------------------------
    # Internal helpers: core logic extracted from desktop_* methods.
    # Accept work_dir/repo so callers can share a single checkout.
    # -----------------------------------------------------------------

    def _do_fetch(self, work_dir: Path, repo: GitRepo) -> "FetchResult":
        """Core fetch logic. Fetches remote and computes ahead/behind."""
        from src.models.contracts.github import FetchResult

        remote_exists = True
        try:
            repo.remotes.origin.fetch(self.branch)
        except Exception as e:
            err_str = str(e).lower()
            if "not found" in err_str or "empty" in err_str or "couldn't find remote ref" in err_str:
                remote_exists = False
            else:
                raise

        ahead = 0
        behind = 0
        if remote_exists and repo.head.is_valid():
            try:
                ahead = int(repo.git.rev_list("--count", f"origin/{self.branch}..HEAD"))
            except Exception:
                ahead = 0
            try:
                behind = int(repo.git.rev_list("--count", f"HEAD..origin/{self.branch}"))
            except Exception:
                behind = 0

        return FetchResult(
            success=True,
            commits_ahead=ahead,
            commits_behind=behind,
            remote_branch_exists=remote_exists,
        )

    def _do_status(self, work_dir: Path, repo: GitRepo) -> "WorkingTreeStatus":
        """Core status logic. Returns changed files and conflicts."""
        from src.models.contracts.github import ChangedFile, MergeConflict, WorkingTreeStatus

        # Check for unresolved conflicts BEFORE git add (which would resolve them)
        conflict_list: list[MergeConflict] = []
        try:
            unmerged = repo.index.unmerged_blobs()
        except Exception:
            unmerged = {}

        if unmerged:
            # Auto-resolve .bifrost/*.yaml manifest conflicts
            try:
                _auto_resolve_manifest_conflicts(repo, work_dir, unmerged)
                unmerged = repo.index.unmerged_blobs()
            except Exception as e:
                logger.warning(f"Manifest auto-resolve in status failed: {e}")

            for cpath in sorted(str(k) for k in unmerged.keys()):
                ours_content = None
                theirs_content = None
                try:
                    ours_content = repo.git.show(f":2:{cpath}")
                except Exception:
                    pass
                try:
                    theirs_content = repo.git.show(f":3:{cpath}")
                except Exception:
                    pass
                metadata = extract_entity_metadata(cpath)
                conflict_list.append(MergeConflict(
                    path=cpath,
                    ours_content=ours_content,
                    theirs_content=theirs_content,
                    display_name=metadata.display_name,
                    entity_type=metadata.entity_type,
                    conflict_type=_classify_conflict_type(unmerged, cpath),
                ))

        # Detect merge state and ahead/behind
        merging = (work_dir / ".git" / "MERGE_HEAD").exists()
        ahead = 0
        behind = 0
        if repo.head.is_valid():
            try:
                ahead = int(repo.git.rev_list("--count", f"origin/{self.branch}..HEAD"))
            except Exception:
                pass
            try:
                behind = int(repo.git.rev_list("--count", f"HEAD..origin/{self.branch}"))
            except Exception:
                pass

        if conflict_list:
            return WorkingTreeStatus(
                changed_files=[],
                total_changes=0,
                conflicts=conflict_list,
                commits_ahead=ahead,
                commits_behind=behind,
                merging=merging,
            )

        # Stage everything to get accurate diff
        repo.git.add(A=True)

        changed: list[ChangedFile] = []

        if repo.head.is_valid():
            porcelain = repo.git.status("--porcelain")
            for line in porcelain.strip().split("\n"):
                if not line.strip():
                    continue
                status_code = line[:2].strip()
                path = line[3:].strip()
                if path.startswith('"') and path.endswith('"'):
                    path = path[1:-1]

                if status_code in ("A", "??"):
                    change_type = "added"
                elif status_code == "D":
                    change_type = "deleted"
                elif status_code == "R":
                    change_type = "renamed"
                    if " -> " in path:
                        path = path.split(" -> ", 1)[1]
                else:
                    change_type = "modified"

                metadata = extract_entity_metadata(path)
                changed.append(ChangedFile(
                    path=path,
                    change_type=change_type,
                    display_name=metadata.display_name,
                    entity_type=metadata.entity_type,
                ))
        else:
            for path in repo.untracked_files:
                metadata = extract_entity_metadata(path)
                changed.append(ChangedFile(
                    path=path,
                    change_type="added",
                    display_name=metadata.display_name,
                    entity_type=metadata.entity_type,
                ))

        # Unstage (reset) so we don't pollute the working tree
        if repo.head.is_valid():
            repo.git.reset("HEAD")

        return WorkingTreeStatus(
            changed_files=changed,
            total_changes=len(changed),
            commits_ahead=ahead,
            commits_behind=behind,
            merging=merging,
        )

    async def _do_commit(self, work_dir: Path, repo: GitRepo, message: str) -> "CommitResult":
        """Core commit logic. Stages, runs preflight, commits."""
        from src.models.contracts.github import CommitResult

        # Regenerate manifest from DB so the commit captures current platform state
        await self._regenerate_manifest_to_dir(self.db, work_dir)
        repo.git.add(A=True)

        # Check if there are changes to commit
        if repo.head.is_valid() and not repo.index.diff("HEAD") and not repo.untracked_files:
            return CommitResult(success=True, files_committed=0)

        # Run preflight
        pf = await self._run_preflight(work_dir)
        if not pf.valid:
            return CommitResult(success=False, error="Preflight validation failed", preflight=pf)

        # Count files
        if repo.head.is_valid():
            file_count = len(repo.index.diff("HEAD")) + len(repo.untracked_files)
        else:
            file_count = len(repo.untracked_files) + len(list(repo.index.diff(None)))

        # Commit
        commit = repo.index.commit(message)

        logger.info(f"Committed {file_count} files: {commit.hexsha[:8]}")
        return CommitResult(
            success=True,
            commit_sha=commit.hexsha,
            files_committed=max(file_count, 1),
            preflight=pf,
        )

    async def _do_pull(self, work_dir: Path, repo: GitRepo, job_id: str | None = None) -> "PullResult":
        """Core pull logic. Fetches, merges, imports entities."""
        from src.models.contracts.github import MergeConflict, PullResult

        async def _progress(phase: str, current: int = 0, total: int = 0) -> None:
            if job_id:
                from src.core.pubsub import publish_git_progress
                await publish_git_progress(job_id, phase, current, total)

        # NOTE: We intentionally do NOT regenerate the manifest here.
        # The sync_execute flow commits first (which regenerates the manifest),
        # then calls _do_pull. Regenerating here would overwrite the
        # manifest with DB state and stash it, causing conflicts with remote.

        # Fetch first
        await _progress("Fetching remote...")
        remote_exists = True
        try:
            repo.remotes.origin.fetch(self.branch)
        except Exception as e:
            err_str = str(e).lower()
            if "not found" in err_str or "empty" in err_str or "couldn't find remote ref" in err_str:
                remote_exists = False
            else:
                raise

        if not remote_exists:
            return PullResult(success=True, pulled=0)

        await _progress("Merging changes...")
        try:
            merge_output = repo.git.merge(f"origin/{self.branch}")
            logger.info(f"Merge succeeded: {merge_output[:200] if merge_output else 'no output'}")
        except Exception as merge_err:
            logger.info(f"Merge failed: {merge_err}")
            is_merge_conflict = (work_dir / ".git" / "MERGE_HEAD").exists()

            if is_merge_conflict:
                conflicts: list[MergeConflict] = []
                try:
                    unmerged = repo.index.unmerged_blobs()
                except Exception:
                    unmerged = {}

                if unmerged:
                    try:
                        _auto_resolve_manifest_conflicts(repo, work_dir, unmerged)
                        unmerged = repo.index.unmerged_blobs()
                    except Exception as e:
                        logger.warning(f"Manifest auto-resolve in pull failed: {e}")

                conflicted_files = sorted(str(k) for k in unmerged.keys())

                if not conflicted_files:
                    # All conflicts were auto-resolved, commit the merge
                    logger.info("All merge conflicts auto-resolved, completing merge")
                    repo.index.commit(
                        "Merge remote-tracking branch (auto-resolved)",
                        parent_commits=[
                            repo.head.commit,
                            repo.commit("MERGE_HEAD"),
                        ],
                    )
                    # Remove MERGE_HEAD to complete merge state
                    merge_head = work_dir / ".git" / "MERGE_HEAD"
                    if merge_head.exists():
                        merge_head.unlink()
                else:
                    for cpath in conflicted_files:
                        ours_content = None
                        theirs_content = None
                        try:
                            ours_content = repo.git.show(f":2:{cpath}")
                        except Exception:
                            pass
                        try:
                            theirs_content = repo.git.show(f":3:{cpath}")
                        except Exception:
                            pass

                        metadata = extract_entity_metadata(cpath)
                        conflicts.append(MergeConflict(
                            path=cpath,
                            ours_content=ours_content,
                            theirs_content=theirs_content,
                            display_name=metadata.display_name,
                            entity_type=metadata.entity_type,
                            conflict_type=_classify_conflict_type(unmerged, cpath),
                        ))

                    logger.info(f"Merge conflict: returning {len(conflicts)} conflicts to UI")
                    return PullResult(
                        success=False,
                        conflicts=conflicts,
                        error="Merge conflicts detected",
                    )
            else:
                raise

        # Entity import is handled by desktop_sync() after push succeeds.
        pulled = 0  # Will be counted during entity import in desktop_sync

        # Sync app preview files from repo to _apps/{id}/preview/
        await self._sync_app_previews(work_dir)

        commit_sha = repo.head.commit.hexsha if repo.head.is_valid() else None
        logger.info(f"Pull complete: {pulled} entities, commit={commit_sha[:8] if commit_sha else 'none'}")
        return PullResult(
            success=True,
            pulled=pulled,
            commit_sha=commit_sha,
        )

    def _do_push(self, work_dir: Path, repo: GitRepo) -> "PushResult":
        """Core push logic. Pushes local commits to remote."""
        from src.models.contracts.github import PushResult

        if not repo.head.is_valid():
            return PushResult(success=True, pushed_commits=0)

        # Count ahead before push
        ahead = 0
        try:
            repo.remotes.origin.fetch(self.branch)
            ahead = int(repo.git.rev_list("--count", f"origin/{self.branch}..HEAD"))
        except Exception:
            ahead = int(repo.git.rev_list("--count", "HEAD"))

        if ahead == 0:
            return PushResult(success=True, pushed_commits=0)

        # Push
        push_infos = repo.remotes.origin.push(refspec=f"HEAD:{self.branch}")

        from git.remote import PushInfo
        for pi in push_infos:
            if pi.flags & PushInfo.ERROR:
                error_msg = pi.summary.strip() if pi.summary else "Push rejected"
                logger.error(f"Push error: {error_msg}")
                return PushResult(success=False, error=error_msg)
            if pi.flags & PushInfo.REJECTED:
                error_msg = f"Push rejected (non-fast-forward): {pi.summary.strip() if pi.summary else ''}"
                logger.error(error_msg)
                return PushResult(success=False, error=error_msg)
            if pi.flags & PushInfo.REMOTE_REJECTED:
                error_msg = f"Push remote-rejected: {pi.summary.strip() if pi.summary else ''}"
                logger.error(error_msg)
                return PushResult(success=False, error=error_msg)

        commit_sha = repo.head.commit.hexsha
        logger.info(f"Pushed {ahead} commits, head={commit_sha[:8]}")
        return PushResult(
            success=True,
            commit_sha=commit_sha,
            pushed_commits=ahead,
        )

    # -----------------------------------------------------------------
    # Desktop-style operations: fetch, status, commit, sync, resolve, diff
    # -----------------------------------------------------------------

    async def desktop_fetch(self, job_id: str | None = None) -> "FetchResult":
        """Git fetch origin. S3 sync down → regenerate manifest → git fetch → ahead/behind."""
        from src.models.contracts.github import FetchResult

        async def _progress(phase: str, current: int = 0, total: int = 0) -> None:
            if job_id:
                from src.core.pubsub import publish_git_progress
                await publish_git_progress(job_id, phase, current, total)

        try:
            await _progress("Syncing from storage...")
            async with self.repo_manager.checkout() as work_dir:
                repo = self._open_or_init(work_dir)
                await _progress("Generating manifest...")
                await self._regenerate_manifest_to_dir(self.db, work_dir)
                await _progress("Fetching remote...")
                return self._do_fetch(work_dir, repo)
        except Exception as e:
            logger.error(f"Fetch failed: {e}", exc_info=True)
            return FetchResult(success=False, error=str(e))

    async def desktop_status(self) -> "WorkingTreeStatus":
        """Get working tree status. No lock, no S3. Returns empty if not initialized."""
        from src.models.contracts.github import WorkingTreeStatus

        try:
            if not self.repo_manager.is_initialized:
                return WorkingTreeStatus()
            async with self.repo_manager.lock() as work_dir:
                repo = self._open_or_init(work_dir)
                return self._do_status(work_dir, repo)
        except Exception as e:
            logger.error(f"Status failed: {e}", exc_info=True)
            return WorkingTreeStatus()

    @staticmethod
    async def _regenerate_manifest_to_dir(db, work_dir) -> None:
        """Generate manifest from DB and write split files to work_dir/.bifrost/."""
        from src.services.manifest import serialize_manifest_dir, MANIFEST_FILES
        from src.services.manifest_generator import generate_manifest

        manifest = await generate_manifest(db)

        # Filter out entities whose files don't exist in work_dir.
        # The DB may contain entities from other workspaces or deleted files;
        # the manifest should only reference files actually present in the repo.
        manifest.workflows = {
            k: v for k, v in manifest.workflows.items()
            if (work_dir / v.path).exists()
        }
        manifest.forms = {
            k: v for k, v in manifest.forms.items()
            if (work_dir / v.path).exists()
        }
        manifest.agents = {
            k: v for k, v in manifest.agents.items()
            if (work_dir / v.path).exists()
        }
        manifest.apps = {
            k: v for k, v in manifest.apps.items()
            if (work_dir / v.path).is_dir()
        }

        # Filter configs to only include those whose integration_id is present
        # in the manifest (or has no integration_id). This prevents stale configs
        # from referencing integrations that aren't part of this repo.
        integration_ids = {v.id for v in manifest.integrations.values()}
        manifest.configs = {
            k: v for k, v in manifest.configs.items()
            if v.integration_id is None or v.integration_id in integration_ids
        }

        files = serialize_manifest_dir(manifest)

        bifrost_dir = work_dir / ".bifrost"
        bifrost_dir.mkdir(parents=True, exist_ok=True)

        for filename, content in files.items():
            (bifrost_dir / filename).write_text(content)

        # Remove files for now-empty entity types
        for filename in MANIFEST_FILES.values():
            path = bifrost_dir / filename
            if filename not in files and path.exists():
                path.unlink()

    async def _reindex_registered_workflows(self, work_dir) -> int:
        """Re-run WorkflowIndexer on all registered workflow .py files."""
        from src.services.file_storage.indexers.workflow import WorkflowIndexer
        from src.models.orm.workflows import Workflow as WfORM
        from sqlalchemy import select

        indexer = WorkflowIndexer(self.db)
        result = await self.db.execute(
            select(WfORM.path).where(WfORM.is_active.is_(True)).distinct()
        )
        paths = [row[0] for row in result.all()]
        count = 0

        for py_path in paths:
            full_path = work_dir / py_path
            if full_path.exists():
                content = full_path.read_bytes()
                await indexer.index_python_file(py_path, content)
                count += 1

        logger.info(f"Re-indexed {count} registered workflow files")
        return count

    async def desktop_commit(self, message: str) -> "CommitResult":
        """
        Commit working tree changes (local only, no push, no S3 sync).
        Runs preflight, commits if valid.
        """
        from src.models.contracts.github import CommitResult

        try:
            async with self.repo_manager.lock() as work_dir:
                repo = self._open_or_init(work_dir)
                return await self._do_commit(work_dir, repo, message)
        except Exception as e:
            logger.error(f"Commit failed: {e}", exc_info=True)
            return CommitResult(success=False, error=str(e))

    async def desktop_sync(self, job_id: str | None = None, confirm_deletes: bool = False) -> "SyncResult":
        """Combined pull + push. The ONLY place entity import + S3 sync-up happen.

        Lock → git pull (stash, merge, pop) → if conflicts: return early.
        If clean: git push → S3 sync up → entity import.
        If stale entities detected and confirm_deletes=False, returns early
        with needs_delete_confirmation=True and the list of pending deletes.
        Returns SyncResult.
        """
        from src.models.contracts.github import SyncResult

        async def _progress(phase: str, current: int = 0, total: int = 0) -> None:
            if job_id:
                from src.core.pubsub import publish_git_progress
                await publish_git_progress(job_id, phase, current, total)

        try:
            async with self.repo_manager.lock() as work_dir:
                repo = self._open_or_init(work_dir)

                # Step 1: Pull (fetch + merge, stash local changes)
                pull_result = await self._do_pull(work_dir, repo, job_id)

                if not pull_result.success:
                    if pull_result.conflicts:
                        # Return conflicts to UI — user resolves via desktop_resolve
                        return SyncResult(
                            success=False,
                            pull_success=False,
                            conflicts=pull_result.conflicts,
                            error="Merge conflicts detected",
                        )
                    return SyncResult(
                        success=False,
                        pull_success=False,
                        error=pull_result.error,
                    )

                # Step 2: Push
                await _progress("Pushing to remote...")
                push_result = self._do_push(work_dir, repo)

                if not push_result.success:
                    return SyncResult(
                        success=False,
                        pull_success=True,
                        push_success=False,
                        error=push_result.error,
                    )

                # Step 3: S3 sync up (so other containers see the changes)
                await _progress("Syncing to storage...")
                await self.repo_manager.sync_up(work_dir)

                # Refresh Redis module cache so editor + workers see new .py content
                from src.core.module_cache import refresh_modules_from_directory
                await refresh_modules_from_directory(work_dir)

                # Step 4: Entity import — always full import (safe, idempotent upserts)
                await _progress("Importing entities...")
                all_entity_changes: list = []
                async with self.db.begin_nested():
                    entities_imported, entity_changes = await self._import_all_entities(
                        work_dir, progress_fn=_progress,
                    )
                    all_entity_changes.extend(entity_changes)
                    await _progress("Updating file index...")
                    await self._update_file_index(work_dir)
                await self.db.commit()

                # Step 5: Clean up removed entities (gated on confirmation)
                await _progress("Checking for removed entities...")
                pending_deletes = await self._detect_stale_entities(work_dir)
                if pending_deletes and not confirm_deletes:
                    # Block sync — user must confirm deletions first
                    logger.info(
                        f"Sync blocked: {len(pending_deletes)} entity deletion(s) require confirmation"
                    )
                    return SyncResult(
                        success=True,
                        needs_delete_confirmation=True,
                        pending_deletes=pending_deletes,
                        pulled=pull_result.pulled,
                        pushed_commits=push_result.pushed_commits,
                        commit_sha=push_result.commit_sha,
                        entities_imported=entities_imported,
                        entity_changes=all_entity_changes,
                    )

                if pending_deletes:
                    await _progress("Deleting removed entities...")
                    async with self.db.begin_nested():
                        deletion_changes = await self._delete_removed_entities(work_dir)
                        all_entity_changes.extend(deletion_changes)
                    await self.db.commit()

                # Step 6: Sync app previews
                await _progress("Syncing app previews...")
                await self._sync_app_previews(work_dir)

                logger.info(
                    f"Sync complete: pushed={push_result.pushed_commits}, "
                    f"imported={entities_imported}, sha={push_result.commit_sha}"
                )
                return SyncResult(
                    success=True,
                    pulled=pull_result.pulled,
                    pushed_commits=push_result.pushed_commits,
                    commit_sha=push_result.commit_sha,
                    entities_imported=entities_imported,
                    entity_changes=all_entity_changes,
                )
        except Exception as e:
            logger.error(f"Sync failed: {e}", exc_info=True)
            return SyncResult(success=False, error=str(e))

    async def desktop_abort_merge(self) -> "AbortMergeResult":
        """Abort an in-progress merge. Returns to pre-pull state."""
        from src.models.contracts.github import AbortMergeResult

        try:
            async with self.repo_manager.lock() as work_dir:
                repo = self._open_or_init(work_dir)

                merge_head = work_dir / ".git" / "MERGE_HEAD"
                if not merge_head.exists():
                    return AbortMergeResult(success=False, error="No merge in progress")

                repo.git.merge("--abort")
                logger.info("Merge aborted successfully")
                return AbortMergeResult(success=True)
        except Exception as e:
            logger.error(f"Abort merge failed: {e}", exc_info=True)
            return AbortMergeResult(success=False, error=str(e))

    def _do_resolve(self, work_dir: Path, repo: GitRepo, resolutions: dict[str, str]) -> "ResolveResult":
        """Core resolve logic for inline conflict resolution during sync_execute."""
        from src.models.contracts.github import ResolveResult

        merge_head = work_dir / ".git" / "MERGE_HEAD"
        is_merge = merge_head.exists()
        has_unmerged = bool(repo.index.unmerged_blobs())

        if not is_merge and not has_unmerged:
            return ResolveResult(success=False, error="No conflicts to resolve")

        for cpath, resolution in resolutions.items():
            try:
                if resolution == "ours":
                    repo.git.checkout("--ours", cpath)
                elif resolution == "theirs":
                    repo.git.checkout("--theirs", cpath)
                repo.git.add(cpath)
            except Exception:
                # DU/UD conflict — one side deleted, checkout fails
                try:
                    repo.git.rm(cpath)
                except Exception:
                    repo.git.add(cpath)

        if is_merge:
            repo.index.commit("Merge with conflict resolution")
        else:
            repo.index.commit("Apply stashed changes with conflict resolution")

        return ResolveResult(success=True)

    async def desktop_resolve(self, resolutions: dict[str, str]) -> "ResolveResult":
        """
        Resolve merge conflicts after a failed pull.
        Applies ours/theirs per file, creates a merge commit.
        NO push, NO S3 sync, NO entity import — those happen when user pushes via sync.
        """
        from src.models.contracts.github import ResolveResult

        try:
            async with self.repo_manager.lock() as work_dir:
                repo = self._open_or_init(work_dir)

                # Check for merge state or unmerged entries (stash pop conflicts)
                merge_head = work_dir / ".git" / "MERGE_HEAD"
                is_merge = merge_head.exists()
                has_unmerged = bool(repo.index.unmerged_blobs())

                if not is_merge and not has_unmerged:
                    return ResolveResult(success=False, error="No conflicts to resolve")

                # Apply resolutions
                for cpath, resolution in resolutions.items():
                    try:
                        if resolution == "ours":
                            repo.git.checkout("--ours", cpath)
                        elif resolution == "theirs":
                            repo.git.checkout("--theirs", cpath)
                        repo.git.add(cpath)
                    except Exception:
                        # DU/UD conflict — one side deleted, checkout fails
                        try:
                            repo.git.rm(cpath)
                        except Exception:
                            repo.git.add(cpath)

                # Complete the operation (merge commit is local)
                if is_merge:
                    # Use git commit (not index.commit) to properly finalize
                    # the merge — this cleans up MERGE_HEAD, MERGE_MSG, etc.
                    repo.git.commit("-m", "Merge with conflict resolution")
                else:
                    repo.index.commit("Apply stashed changes with conflict resolution")

                # Compute ahead/behind so the UI can update immediately
                ahead = 0
                behind = 0
                try:
                    ahead = int(repo.git.rev_list("--count", f"origin/{self.branch}..HEAD"))
                except Exception:
                    pass
                try:
                    behind = int(repo.git.rev_list("--count", f"HEAD..origin/{self.branch}"))
                except Exception:
                    pass

                logger.info("Resolved conflicts, created merge commit (local)")
                return ResolveResult(success=True, commits_ahead=ahead, commits_behind=behind)
        except Exception as e:
            logger.error(f"Resolve failed: {e}", exc_info=True)
            return ResolveResult(success=False, error=str(e))

    async def desktop_diff(self, path: str) -> "DiffResult":
        """Get file diff: HEAD content vs working tree content. No S3 sync."""
        from src.models.contracts.github import DiffResult

        try:
            async with self.repo_manager.lock() as work_dir:
                repo = self._open_or_init(work_dir)

                # Get HEAD content
                head_content = None
                if repo.head.is_valid():
                    try:
                        head_content = repo.git.show(f"HEAD:{path}")
                    except Exception:
                        pass  # File doesn't exist in HEAD (new file)

                # Get working tree content
                working_content = None
                working_path = work_dir / path
                if working_path.exists():
                    working_content = working_path.read_text(errors="replace")

                return DiffResult(
                    path=path,
                    head_content=head_content,
                    working_content=working_content,
                )
        except Exception as e:
            logger.error(f"Diff failed: {e}", exc_info=True)
            return DiffResult(path=path)

    async def desktop_discard(self, paths: list[str]) -> "DiscardResult":
        """Discard working tree changes for specific files. S3 sync up so API sees revert."""
        from src.models.contracts.github import DiscardResult

        try:
            async with self.repo_manager.lock() as work_dir:
                repo = self._open_or_init(work_dir)
                discarded = []

                for path in paths:
                    file_path = work_dir / path
                    try:
                        if repo.head.is_valid():
                            try:
                                # File exists in HEAD — restore it
                                repo.git.checkout("HEAD", "--", path)
                                discarded.append(path)
                                continue
                            except Exception:
                                pass
                        # Untracked or not in HEAD — just delete
                        if file_path.exists():
                            file_path.unlink()
                            discarded.append(path)
                    except Exception as e:
                        logger.warning(f"Failed to discard {path}: {e}")

                # S3 sync up so other containers see the reverted files
                await self.repo_manager.sync_up(work_dir)

                # Refresh Redis module cache so editor + workers see reverted .py content
                from src.core.module_cache import refresh_modules_from_directory
                await refresh_modules_from_directory(work_dir)

                logger.info(f"Discarded {len(discarded)} file(s)")
                return DiscardResult(success=True, discarded=discarded)
        except Exception as e:
            logger.error(f"Discard failed: {e}", exc_info=True)
            return DiscardResult(success=False, error=str(e))

    # -----------------------------------------------------------------
    # Helpers for desktop-style operations
    # -----------------------------------------------------------------

    def _open_or_init(self, work_dir: Path) -> GitRepo:
        """Open existing .git/ or clone fresh. Ensure remote URL and user identity are set."""
        if (work_dir / ".git").exists():
            repo = GitRepo(str(work_dir))
            if "origin" in [r.name for r in repo.remotes]:
                repo.remotes.origin.set_url(self.repo_url)
            else:
                repo.create_remote("origin", self.repo_url)
        else:
            repo = self._clone_or_init(work_dir)

        # Ensure git user identity is configured (needed for merge/commit)
        with repo.config_writer() as cw:
            try:
                cw.get_value("user", "name")
            except Exception:
                cw.set_value("user", "name", "Bifrost")
            try:
                cw.get_value("user", "email")
            except Exception:
                cw.set_value("user", "email", "bifrost@localhost")

        return repo

    async def _execute_ops(self, ops: "list[SyncOp]") -> int:
        """Execute a list of SyncOps against the DB in order.

        Returns the number of ops executed.
        """
        from src.services.sync_ops import SyncOp  # noqa: F401
        for op in ops:
            await op.execute(self.db)
        return len(ops)

    @staticmethod
    def _ops_to_issues(ops: "list[SyncOp]") -> list[str]:
        """Convert a list of SyncOps to human-readable validation issues.

        Currently returns an empty list — resolution methods detect missing
        refs by logging warnings and skipping. Future work can add issue
        markers to ops for richer dry-run output.
        """
        return []

    async def _prefetch_existing_entities(self) -> dict:
        """Prefetch all existing entity IDs/natural-keys in bulk queries.

        Returns a cache dict that _resolve_* methods use for O(1) lookups
        instead of per-entity SELECT queries.
        """
        from src.models.orm.applications import Application
        from src.models.orm.config import Config
        from src.models.orm.integrations import (
            Integration,
            IntegrationConfigSchema,
            IntegrationMapping,
        )
        from src.models.orm.organizations import Organization
        from src.models.orm.tables import Table
        from src.models.orm.users import Role
        from src.models.orm.workflows import Workflow

        cache: dict = {}

        # Organizations: {id} set + {name: id} dict
        org_result = await self.db.execute(select(Organization.id, Organization.name))
        cache["org_ids"] = set()
        cache["org_by_name"] = {}
        for row in org_result.all():
            cache["org_ids"].add(row[0])
            cache["org_by_name"][row[1]] = row[0]

        # Roles: {id} set + {name: id} dict
        role_result = await self.db.execute(select(Role.id, Role.name))
        cache["role_ids"] = set()
        cache["role_by_name"] = {}
        for row in role_result.all():
            cache["role_ids"].add(row[0])
            cache["role_by_name"][row[1]] = row[0]

        # Workflows: {(path, function_name): id} + {id} set
        wf_result = await self.db.execute(
            select(Workflow.id, Workflow.path, Workflow.function_name)
        )
        cache["wf_ids"] = set()
        cache["wf_by_natural"] = {}
        for row in wf_result.all():
            cache["wf_ids"].add(row[0])
            if row[1] and row[2]:
                cache["wf_by_natural"][(row[1], row[2])] = row[0]

        # Integrations: {name: id} + {id} set
        integ_result = await self.db.execute(select(Integration.id, Integration.name))
        cache["integ_ids"] = set()
        cache["integ_by_name"] = {}
        for row in integ_result.all():
            cache["integ_ids"].add(row[0])
            cache["integ_by_name"][row[1]] = row[0]

        # IntegrationConfigSchema: {integ_id: {key: schema_obj}}
        cs_result = await self.db.execute(select(IntegrationConfigSchema))
        cache["integ_cs"] = {}
        for cs in cs_result.scalars().all():
            cache["integ_cs"].setdefault(cs.integration_id, {})[cs.key] = cs

        # IntegrationMapping: {integ_id: {org_id_str: mapping_obj}}
        im_result = await self.db.execute(select(IntegrationMapping))
        cache["integ_mappings"] = {}
        for m in im_result.scalars().all():
            org_key = str(m.organization_id) if m.organization_id else None
            cache["integ_mappings"].setdefault(m.integration_id, {})[org_key] = m

        # Apps: {slug: id}
        app_result = await self.db.execute(select(Application.id, Application.slug))
        cache["app_by_slug"] = {}
        for row in app_result.all():
            cache["app_by_slug"][row[1]] = row[0]

        # Tables: {(name, org_id): id} + {id} set
        table_result = await self.db.execute(
            select(Table.id, Table.name, Table.organization_id)
        )
        cache["table_ids"] = set()
        cache["table_by_natural"] = {}
        for row in table_result.all():
            cache["table_ids"].add(row[0])
            cache["table_by_natural"][(row[1], row[2])] = row[0]

        # Configs: {(key, integ_id, org_id): (id, value, config_schema_id)}
        cfg_result = await self.db.execute(
            select(Config.id, Config.key, Config.integration_id, Config.organization_id, Config.value, Config.config_schema_id)
        )
        cache["config_by_natural"] = {}
        for row in cfg_result.all():
            cache["config_by_natural"][(row[1], row[2], row[3])] = (row[0], row[4], row[5])

        return cache

    async def plan_import(self, manifest: "Manifest", work_dir: Path | None = None, progress_fn=None, repo: "RepoStorage | None" = None, dry_run: bool = False) -> "list[SyncOp]":
        """Build and execute SyncOps for importing a manifest (entities only).

        Resolves and immediately executes ops in dependency order.
        Uses prefetch cache to minimize per-entity DB lookups.
        Deletions are handled separately by _delete_removed_entities / _resolve_deletions.
        Indexer side-effects (WorkflowIndexer, FormIndexer, AgentIndexer) remain
        in _import_all_entities.

        File reads use either ``repo`` (direct S3 via RepoStorage) or
        ``work_dir`` (local filesystem).  At least one must be provided for
        entities that reference source files (workflows, forms, agents).

        Import order:
        0a. Organizations (no deps)
        0b. Roles (no deps)
        1.  Workflows (refs org_id)
        2.  Integrations (refs workflow UUIDs for data_provider)
        3.  Configs (refs integration + org UUIDs)
        4.  Apps (refs org UUIDs)
        5.  Tables (refs org + app UUIDs)
        6.  Event Sources + Subscriptions (refs integration + workflow UUIDs)
        7.  Forms (refs workflow + org UUIDs) — metadata only
        8.  Agents (refs workflow + org UUIDs) — metadata only

        Returns the collected ops for callers that want to inspect them
        (e.g. for entity change tracking or dry-run analysis).
        """
        from src.services.sync_ops import SyncOp, Upsert  # noqa: F401

        if not work_dir and not repo:
            raise ValueError("plan_import requires either work_dir or repo")

        all_ops: list[SyncOp] = []

        # Helpers: abstract file reads over repo (S3) or work_dir (filesystem)
        async def _file_exists(path: str) -> bool:
            if repo:
                return await repo.exists(path)
            elif work_dir:
                return (work_dir / path).exists()
            return False

        async def _file_read(path: str) -> bytes | None:
            if repo:
                try:
                    return await repo.read(path)
                except Exception:
                    return None
            elif work_dir:
                p = work_dir / path
                if p.exists():
                    return p.read_bytes()
            return None

        # Count total entities for progress tracking
        total = (len(manifest.organizations) + len(manifest.roles)
                 + len(manifest.workflows) + len(manifest.integrations)
                 + len(manifest.configs) + len(manifest.apps)
                 + len(manifest.tables) + len(manifest.events)
                 + len(manifest.forms) + len(manifest.agents))
        current = 0

        async def _prog(msg: str) -> None:
            nonlocal current
            current += 1
            if progress_fn:
                await progress_fn(msg, current, total)

        # Prefetch all existing entities for O(1) lookups
        cache = await self._prefetch_existing_entities()

        # 0a. Resolve organizations (no deps) — execute immediately
        org_ops: list[SyncOp] = []
        for morg in manifest.organizations:
            await _prog(f"Importing organization: {morg.name}")
            org_ops.extend(self._resolve_organization(morg, cache))
        for op in org_ops:
            if dry_run:
                if isinstance(op, Upsert):
                    op.action_taken = "updated" if op.id in cache.get("org_ids", set()) else "inserted"
            else:
                await op.execute(self.db)
        all_ops.extend(org_ops)

        # 0b. Resolve roles (no deps) — execute immediately
        role_ops: list[SyncOp] = []
        for mrole in manifest.roles:
            await _prog(f"Importing role: {mrole.name}")
            role_ops.extend(self._resolve_role(mrole, cache))
        for op in role_ops:
            if dry_run:
                if isinstance(op, Upsert):
                    op.action_taken = "updated" if op.id in cache.get("role_ids", set()) else "inserted"
            else:
                await op.execute(self.db)
        all_ops.extend(role_ops)

        # 1. Resolve workflows — execute immediately
        # Track which workflow IDs were actually imported (file exists in repo/disk)
        imported_wf_ids: set[str] = set()
        for key, mwf in manifest.workflows.items():
            if await _file_exists(mwf.path):
                await _prog(f"Importing workflow: {mwf.name or key}")
                wf_ops = self._resolve_workflow(mwf.name or key, mwf, cache)
                for op in wf_ops:
                    if dry_run:
                        if isinstance(op, Upsert):
                            op.action_taken = "updated" if op.id in cache.get("wf_ids", set()) else "inserted"
                    else:
                        await op.execute(self.db)
                all_ops.extend(wf_ops)
                imported_wf_ids.add(mwf.id)

        # 2. Resolve integrations (with config_schema, oauth_provider, mappings)
        for key, minteg in manifest.integrations.items():
            await _prog(f"Importing integration: {minteg.name or key}")
            integ_ops = await self._resolve_integration(minteg.name or key, minteg, cache)
            for op in integ_ops:
                if dry_run:
                    if isinstance(op, Upsert):
                        op.action_taken = "updated" if op.id in cache.get("integ_ids", set()) else "inserted"
                else:
                    await op.execute(self.db)
            all_ops.extend(integ_ops)

        # 3. Resolve configs
        _config_id_set = {v[0] for v in cache.get("config_by_natural", {}).values()}
        for _config_key, mcfg in manifest.configs.items():
            cfg_ops = self._resolve_config(mcfg, cache)
            for op in cfg_ops:
                if dry_run:
                    if isinstance(op, Upsert):
                        op.action_taken = "updated" if op.id in _config_id_set else "inserted"
                else:
                    await op.execute(self.db)
            all_ops.extend(cfg_ops)

        # 4. Resolve apps (before tables — tables ref application_id)
        _app_id_set = set(cache.get("app_by_slug", {}).values())
        for _app_name, mapp in manifest.apps.items():
            await _prog(f"Importing app: {mapp.name}")
            app_ops = self._resolve_app(mapp, cache)
            for op in app_ops:
                if dry_run:
                    if isinstance(op, Upsert):
                        op.action_taken = "updated" if op.id in _app_id_set else "inserted"
                else:
                    await op.execute(self.db)
            all_ops.extend(app_ops)

        # 5. Resolve tables (refs org + app UUIDs)
        for key, mtable in manifest.tables.items():
            await _prog(f"Importing table: {mtable.name or key}")
            table_ops = await self._resolve_table(mtable.name or key, mtable, cache)
            for op in table_ops:
                if dry_run:
                    if isinstance(op, Upsert):
                        op.action_taken = "updated" if op.id in cache.get("table_ids", set()) else "inserted"
                else:
                    await op.execute(self.db)
            all_ops.extend(table_ops)

        # 6. Resolve event sources + subscriptions
        for key, mes in manifest.events.items():
            await _prog(f"Importing event source: {mes.name or key}")
            es_ops = await self._resolve_event_source(mes.name or key, mes, imported_wf_ids)
            for op in es_ops:
                if dry_run:
                    if isinstance(op, Upsert):
                        op.action_taken = "inserted"  # no ES cache; assume new
                else:
                    await op.execute(self.db)
            all_ops.extend(es_ops)

        # 7. Resolve forms (metadata ops only — indexer called in _import_all_entities)
        for _form_name, mform in manifest.forms.items():
            content = await _file_read(mform.path)
            if content is not None:
                await _prog(f"Importing form: {mform.name}")
                form_ops = self._resolve_form(mform, content)
                for op in form_ops:
                    if dry_run:
                        if isinstance(op, Upsert):
                            op.action_taken = "inserted"  # no form cache; assume new
                    else:
                        await op.execute(self.db)
                all_ops.extend(form_ops)

        # 8. Resolve agents (metadata ops only — indexer called in _import_all_entities)
        for _agent_name, magent in manifest.agents.items():
            content = await _file_read(magent.path)
            if content is not None:
                await _prog(f"Importing agent: {magent.name}")
                agent_ops = self._resolve_agent(magent, content)
                for op in agent_ops:
                    if dry_run:
                        if isinstance(op, Upsert):
                            op.action_taken = "inserted"  # no agent cache; assume new
                    else:
                        await op.execute(self.db)
                all_ops.extend(agent_ops)

        return all_ops

    async def _import_all_entities(
        self,
        work_dir: Path,
        progress_fn=None,
    ) -> "tuple[int, list]":
        """Import all entities from the working tree into the DB.

        Delegates to plan_import which resolves and immediately executes ops,
        then runs indexer side-effects for workflows, forms, and agents.

        Returns tuple of (count of entities imported, list of entity changes).
        """
        from uuid import UUID
        from src.models.contracts.github import EntityChange

        bifrost_dir = work_dir / ".bifrost"
        manifest = read_manifest_from_dir(bifrost_dir)

        has_entities = (
            manifest.organizations or manifest.roles
            or manifest.workflows or manifest.forms or manifest.agents or manifest.apps
            or manifest.integrations or manifest.configs or manifest.tables
            or manifest.events
        )
        if not has_entities:
            return 0, []

        count = 0

        async def _prog(msg: str) -> None:
            if progress_fn:
                await progress_fn(msg, 0, 0)

        # Run all resolve ops (including immediate execution inside plan_import)
        await _prog("Resolving entities from manifest...")
        all_ops = await self.plan_import(manifest, work_dir, progress_fn=progress_fn)

        # Collect entity changes from upsert ops
        from src.services.sync_ops import Upsert
        entity_changes: list[EntityChange] = []
        for op in all_ops:
            if isinstance(op, Upsert) and op.action_taken:
                action = "added" if op.action_taken == "inserted" else "updated"
                entity_name = op.values.get("name") or op.values.get("function_name") or str(op.id)
                entity_type = getattr(op.model, "__tablename__", "unknown")
                entity_changes.append(EntityChange(
                    action=action,
                    entity_type=entity_type,
                    name=entity_name,
                ))

        # Count imported entities
        count += len(manifest.organizations)
        count += len(manifest.roles)
        count += sum(1 for mwf in manifest.workflows.values() if (work_dir / mwf.path).exists())
        count += len(manifest.integrations)
        count += len(manifest.configs)
        count += len(manifest.apps)
        count += len(manifest.tables)
        count += len(manifest.events)

        # Indexer side-effects: WorkflowIndexer for each workflow
        # Enriches parameters_schema, description, etc. from AST
        await _prog("Indexing workflows...")
        from src.models.orm.workflows import Workflow as WfORM
        from src.services.file_storage.indexers.workflow import WorkflowIndexer

        # Prefetch all workflows by path for the indexer (1 query instead of N)
        wf_paths = {mwf.path for mwf in manifest.workflows.values() if (work_dir / mwf.path).exists()}
        if wf_paths:
            wf_result = await self.db.execute(
                select(WfORM).where(WfORM.path.in_(wf_paths))
            )
            wf_cache: dict[tuple[str, str], WfORM] = {}
            for wf in wf_result.scalars().all():
                if wf.path and wf.function_name:
                    wf_cache[(wf.path, wf.function_name)] = wf
        else:
            wf_cache = {}

        workflow_indexer = WorkflowIndexer(self.db)
        workflow_indexer.set_prefetch_cache(wf_cache)
        for _wf_name, mwf in manifest.workflows.items():
            wf_path = work_dir / mwf.path
            if wf_path.exists():
                content = wf_path.read_bytes()
                await workflow_indexer.index_python_file(mwf.path, content)

        await _prog("Indexing forms...")
        # Indexer side-effects: FormIndexer for each form
        from src.services.file_storage.indexers.form import FormIndexer
        form_indexer = FormIndexer(self.db)
        for _form_name, mform in manifest.forms.items():
            form_path = work_dir / mform.path
            if form_path.exists():
                content = form_path.read_bytes()
                data = yaml.safe_load(content.decode("utf-8"))
                if data:
                    data["id"] = mform.id
                    # Resolve portable refs (path::function_name) to UUIDs
                    await self._resolve_ref_field(data, "workflow_id")
                    await self._resolve_ref_field(data, "launch_workflow_id")
                    updated_content = (yaml.dump(data, default_flow_style=False, sort_keys=True).rstrip() + "\n").encode("utf-8")
                    await form_indexer.index_form(f"forms/{mform.id}.form.yaml", updated_content)

                    # Post-indexer: update org_id and access_level (indexer skips these)
                    from sqlalchemy import update as sa_update
                    from src.models.orm.forms import Form
                    org_id_uuid = UUID(mform.organization_id) if mform.organization_id else None
                    form_id_uuid = UUID(mform.id)
                    post_values: dict = {}
                    if org_id_uuid:
                        post_values["organization_id"] = org_id_uuid
                    if hasattr(mform, "access_level") and mform.access_level:
                        post_values["access_level"] = mform.access_level
                    if post_values:
                        post_values["updated_at"] = datetime.now(timezone.utc)
                        await self.db.execute(
                            sa_update(Form).where(Form.id == form_id_uuid).values(**post_values)
                        )
                count += 1

        await _prog("Indexing agents...")
        # Indexer side-effects: AgentIndexer for each agent
        from src.services.file_storage.indexers.agent import AgentIndexer
        agent_indexer = AgentIndexer(self.db)
        for _agent_name, magent in manifest.agents.items():
            agent_path = work_dir / magent.path
            if agent_path.exists():
                content = agent_path.read_bytes()
                data = yaml.safe_load(content.decode("utf-8"))
                if data:
                    data["id"] = magent.id
                    # Resolve portable refs (path::function_name) to UUIDs in tool_ids
                    await self._resolve_ref_field(data, "tool_ids")
                    if "tools" in data and "tool_ids" not in data:
                        await self._resolve_ref_field(data, "tools")
                    updated_content = (yaml.dump(data, default_flow_style=False, sort_keys=True).rstrip() + "\n").encode("utf-8")
                    await agent_indexer.index_agent(f"agents/{magent.id}.agent.yaml", updated_content)

                    # Post-indexer: update org_id and access_level (indexer skips these)
                    from sqlalchemy import update as sa_update
                    from src.models.orm.agents import Agent
                    org_id_uuid = UUID(magent.organization_id) if magent.organization_id else None
                    agent_id_uuid = UUID(magent.id)
                    post_values_a: dict = {}
                    if org_id_uuid:
                        post_values_a["organization_id"] = org_id_uuid
                    if hasattr(magent, "access_level") and magent.access_level:
                        post_values_a["access_level"] = magent.access_level
                    if post_values_a:
                        post_values_a["updated_at"] = datetime.now(timezone.utc)
                        await self.db.execute(
                            sa_update(Agent).where(Agent.id == agent_id_uuid).values(**post_values_a)
                        )
                count += 1

        return count, entity_changes

    async def _delete_removed_entities(self, work_dir: Path | None = None, manifest: "Manifest | None" = None, repo: "RepoStorage | None" = None) -> list:
        """Delete entities that disappeared from the manifest after a pull.

        Delegates to _resolve_deletions which executes bulk deletes inline.
        Returns list of EntityChange entries for removed entities.
        """
        return await self._resolve_deletions(work_dir=work_dir, manifest=manifest, repo=repo)

    # -----------------------------------------------------------------
    # App preview sync
    # -----------------------------------------------------------------

    async def _sync_app_previews(self, work_dir: Path) -> None:
        """Sync app preview files from repo working tree to _apps/{id}/preview/ in S3.

        Reads the manifest to find app entries, derives the source directory
        from each app's path, and copies files to the preview store.
        """
        from src.services.app_storage import AppStorageService

        bifrost_dir = work_dir / ".bifrost"
        manifest = read_manifest_from_dir(bifrost_dir)

        if not manifest.apps:
            return

        import asyncio

        app_storage = AppStorageService(self.repo_manager._settings)

        async def _sync_one_app(mapp_id: str, source_dir: str) -> None:
            try:
                synced, compile_errors = await app_storage.sync_preview_compiled(
                    mapp_id, source_dir
                )
                logger.info(f"Synced {synced} compiled preview files for app {mapp_id}")
                if compile_errors:
                    logger.warning(
                        f"Compile errors for app {mapp_id}: {compile_errors}"
                    )
            except Exception as e:
                logger.warning(f"Failed to sync preview for app {mapp_id}: {e}")

        # Process all apps concurrently
        await asyncio.gather(*(
            _sync_one_app(mapp.id, mapp.path)
            for mapp in manifest.apps.values()
        ))

    # -----------------------------------------------------------------
    # Reimport from repo (no git operations)
    # -----------------------------------------------------------------

    async def reimport_from_repo(self) -> int:
        """Re-import all entities from S3 _repo/ without git operations.

        Downloads the working tree from S3, imports entities into DB,
        updates file_index, and syncs app previews.

        Returns count of entities imported.
        """
        async with self.repo_manager.checkout() as work_dir:
            # Regenerate manifest from current DB state
            await self._regenerate_manifest_to_dir(self.db, work_dir)

            # Import entities atomically with savepoint
            async with self.db.begin_nested():
                count, _changes = await self._import_all_entities(work_dir)
                await self._delete_removed_entities(work_dir)
                await self._update_file_index(work_dir)
            await self.db.commit()

            # Re-run indexers on all registered workflow files
            await self._reindex_registered_workflows(work_dir)
            await self.db.commit()

            # Sync app preview files
            await self._sync_app_previews(work_dir)

            logger.info(f"Reimport complete: {count} entities")
            return count

    # -----------------------------------------------------------------
    # Internal: git operations
    # -----------------------------------------------------------------

    def _clone_or_init(self, target: Path) -> GitRepo:
        """Clone from repo_url, or init if repo is empty.

        Handles the case where target already has files (e.g. entity files
        written by RepoSyncWriter before the first clone). Clones into a
        temp dir and merges .git/ + remote files into target.
        """
        import shutil
        import tempfile

        try:
            # Clone into a temp dir first (git clone requires clean dir)
            clone_dir = Path(tempfile.mkdtemp(prefix="bifrost-clone-"))
            try:
                repo = GitRepo.clone_from(
                    self.repo_url,
                    str(clone_dir),
                    branch=self.branch,
                )
                # Move .git/ to the target
                shutil.move(str(clone_dir / ".git"), str(target / ".git"))
                # Copy any tracked files from clone that aren't in target
                for item in clone_dir.iterdir():
                    if item.name == ".git":
                        continue
                    dest = target / item.name
                    if not dest.exists():
                        if item.is_dir():
                            shutil.copytree(str(item), str(dest))
                        else:
                            shutil.copy2(str(item), str(dest))
                    else:
                        logger.info(f"Skipping remote file {item.name} — already exists in working tree")
                # Open the repo at target
                return GitRepo(str(target))
            finally:
                shutil.rmtree(clone_dir, ignore_errors=True)
        except Exception as e:
            err_str = str(e)
            # Empty repo or branch doesn't exist yet
            if "not found" in err_str.lower() or "empty" in err_str.lower() or "could not find remote branch" in err_str.lower():
                repo = GitRepo.init(str(target))
                repo.create_remote("origin", self.repo_url)
                return repo
            raise SyncError(f"Failed to clone {self.repo_url}: {e}") from e

    # -----------------------------------------------------------------
    # Internal: import entities from repo
    # -----------------------------------------------------------------

    def _resolve_organization(self, morg, cache: dict) -> "list[SyncOp]":
        """Resolve an organization from manifest into SyncOps.

        ID-first, name-fallback upsert strategy using prefetch cache.
        Returns ops list without executing.
        """
        from uuid import UUID

        from src.models.orm.organizations import Organization
        from src.services.sync_ops import SyncOp, Upsert  # noqa: F401

        org_id = UUID(morg.id)

        # 1. Try by ID first (handles renames)
        if org_id in cache["org_ids"]:
            return [Upsert(
                model=Organization,
                id=org_id,
                values={"name": morg.name, "is_active": True},
                match_on="id",
            )]

        # 2. Try by name (cross-env ID sync)
        existing_by_name = cache["org_by_name"].get(morg.name)
        if existing_by_name is not None:
            return [Upsert(
                model=Organization,
                id=org_id,
                values={"id": org_id, "name": morg.name, "is_active": True},
                match_on="name",
            )]

        # 3. Insert new
        return [Upsert(
            model=Organization,
            id=org_id,
            values={"name": morg.name, "is_active": True, "created_by": "git-sync"},
            match_on="id",
        )]

    def _resolve_role(self, mrole, cache: dict) -> "list[SyncOp]":
        """Resolve a role from manifest into SyncOps.

        ID-first, name-fallback upsert strategy using prefetch cache.
        Returns ops list without executing.
        """
        from uuid import UUID

        from src.models.orm.users import Role
        from src.services.sync_ops import SyncOp, Upsert  # noqa: F401

        role_id = UUID(mrole.id)

        # 1. Try by ID first (handles renames)
        if role_id in cache["role_ids"]:
            return [Upsert(
                model=Role,
                id=role_id,
                values={"name": mrole.name, "is_active": True},
                match_on="id",
            )]

        # 2. Try by name (cross-env ID sync)
        existing_by_name = cache["role_by_name"].get(mrole.name)
        if existing_by_name is not None:
            return [Upsert(
                model=Role,
                id=role_id,
                values={"id": role_id, "name": mrole.name, "is_active": True},
                match_on="name",
            )]

        # 3. Insert new
        return [Upsert(
            model=Role,
            id=role_id,
            values={"name": mrole.name, "is_active": True, "created_by": "git-sync"},
            match_on="id",
        )]

    async def _sync_role_assignments(self, entity_id, manifest_roles: list[str], junction_model, entity_fk_name: str) -> None:
        """Sync role assignments for an entity: add first, then remove (no permission gap).

        Args:
            entity_id: The entity's UUID
            manifest_roles: List of role UUID strings from manifest
            junction_model: The ORM model for the junction table (e.g. WorkflowRole)
            entity_fk_name: The FK column name on the junction table (e.g. 'workflow_id')
        """
        from uuid import UUID

        from sqlalchemy import delete as sa_delete
        from sqlalchemy.dialects.postgresql import insert

        desired_role_ids = {UUID(r) for r in manifest_roles}

        # Get current assignments
        entity_fk_col = getattr(junction_model, entity_fk_name)
        role_id_col = getattr(junction_model, "role_id")
        result = await self.db.execute(
            select(role_id_col).where(entity_fk_col == entity_id)
        )
        current_role_ids = {row[0] for row in result.all()}

        # ADD new assignments first (no permission gap)
        for role_id in desired_role_ids - current_role_ids:
            stmt = insert(junction_model).values(**{
                entity_fk_name: entity_id,
                "role_id": role_id,
                "assigned_by": "git-sync",
            }).on_conflict_do_nothing()
            await self.db.execute(stmt)

        # THEN remove stale assignments
        for role_id in current_role_ids - desired_role_ids:
            await self.db.execute(
                sa_delete(junction_model).where(
                    entity_fk_col == entity_id,
                    role_id_col == role_id,
                )
            )

    def _resolve_workflow(self, manifest_name: str, mwf, cache: dict) -> "list[SyncOp]":
        """Resolve a workflow from manifest into SyncOps.

        Uses prefetch cache for natural-key (path+function_name) or ID lookup.
        Returns ops list without executing.
        """
        from uuid import UUID

        from src.models.orm.workflow_roles import WorkflowRole
        from src.models.orm.workflows import Workflow
        from src.services.sync_ops import SyncOp, SyncRoles, Upsert  # noqa: F401

        wf_id = UUID(mwf.id)
        org_id = UUID(mwf.organization_id) if mwf.organization_id else None

        # Check prefetch cache for existing workflow
        existing_by_natural = cache["wf_by_natural"].get((mwf.path, mwf.function_name))
        existing_by_id = wf_id if wf_id in cache["wf_ids"] else None

        wf_values = {
            "name": manifest_name,
            "function_name": mwf.function_name,
            "path": mwf.path,
            "type": getattr(mwf, "type", "workflow"),
            "is_active": True,
            "organization_id": org_id,
            "access_level": getattr(mwf, "access_level", "role_based"),
            "endpoint_enabled": getattr(mwf, "endpoint_enabled", False),
            "timeout_seconds": getattr(mwf, "timeout_seconds", 1800),
            "public_endpoint": getattr(mwf, "public_endpoint", False),
            "category": getattr(mwf, "category", "General"),
            "tags": getattr(mwf, "tags", []),
        }

        # Only include description if manifest explicitly provides it
        if mwf.description is not None:
            wf_values["description"] = mwf.description

        ops: list[SyncOp] = []

        if existing_by_natural is not None:
            # Match on natural key — update (including ID if it changed)
            ops.append(Upsert(
                model=Workflow,
                id=existing_by_natural,
                values={"id": wf_id, **wf_values},
                match_on="id",
            ))
        elif existing_by_id is not None:
            # Same ID but path/function changed (rename) — update
            ops.append(Upsert(
                model=Workflow,
                id=wf_id,
                values=wf_values,
                match_on="id",
            ))
        else:
            # New workflow — insert
            ops.append(Upsert(
                model=Workflow,
                id=wf_id,
                values=wf_values,
                match_on="id",
            ))

        # Role sync op
        if hasattr(mwf, "roles") and mwf.roles:
            role_ids = {UUID(r) for r in mwf.roles}
            ops.append(SyncRoles(
                junction_model=WorkflowRole,
                entity_fk="workflow_id",
                entity_id=wf_id,
                role_ids=role_ids,
            ))

        return ops

    async def _resolve_workflow_ref(self, ref: str) -> "UUID | None":
        """Resolve a workflow reference: try UUID, then path::function_name, then name.

        Used by event subscription sync to support flexible workflow_id formats
        in the manifest (UUID, path::func, or workflow name).

        Returns UUID if found, None otherwise.
        """
        from uuid import UUID

        from src.models.orm.workflows import Workflow

        # 1. Try as UUID — direct ID match
        try:
            wf_id = UUID(ref)
            result = await self.db.execute(select(Workflow.id).where(Workflow.id == wf_id))
            if result.scalar_one_or_none():
                return wf_id
        except ValueError:
            pass

        # 2. Try as path::function_name
        if "::" in ref:
            path, func = ref.rsplit("::", 1)
            result = await self.db.execute(
                select(Workflow.id).where(Workflow.path == path, Workflow.function_name == func)
            )
            wf_id = result.scalar_one_or_none()
            if wf_id:
                return wf_id

        # 3. Try as workflow name
        result = await self.db.execute(select(Workflow.id).where(Workflow.name == ref))
        wf_id = result.scalar_one_or_none()
        if wf_id:
            return wf_id

        return None

    async def _resolve_portable_ref(self, ref: str) -> str | None:
        """Resolve a path::function_name portable ref to a workflow UUID string.

        Args:
            ref: A string like "workflows/foo.py::bar"

        Returns:
            UUID string if found, None otherwise
        """
        from src.models.orm.workflows import Workflow

        if "::" not in ref:
            return None

        path, _, function_name = ref.rpartition("::")
        if not path or not function_name:
            return None

        result = await self.db.execute(
            select(Workflow.id).where(
                Workflow.path == path,
                Workflow.function_name == function_name,
                Workflow.is_active.is_(True),
            )
        )
        wf_id = result.scalar_one_or_none()
        return str(wf_id) if wf_id else None

    async def _resolve_ref_field(self, data: dict, field_name: str) -> None:
        """Resolve a portable ref in a dict field to a UUID in-place.

        If the field value contains '::', attempts to resolve it.
        If resolution fails, the value is left unchanged (will be stored as-is).
        """
        value = data.get(field_name)
        if isinstance(value, str) and "::" in value:
            resolved = await self._resolve_portable_ref(value)
            if resolved:
                data[field_name] = resolved
                logger.info(f"Resolved portable ref '{value}' -> '{resolved}'")
            else:
                logger.warning(f"Could not resolve portable ref '{value}' for field '{field_name}'")
        elif isinstance(value, list):
            # Handle list fields like tool_ids
            resolved_list = []
            for item in value:
                if isinstance(item, str) and "::" in item:
                    resolved = await self._resolve_portable_ref(item)
                    resolved_list.append(resolved if resolved else item)
                else:
                    resolved_list.append(item)
            data[field_name] = resolved_list

    async def _resolve_deletions(self, work_dir: Path | None = None, manifest: "Manifest | None" = None, repo: "RepoStorage | None" = None, dry_run: bool = False) -> list:
        """Compute delete/deactivate ops for entities removed from the manifest.

        Optimized: pushes filtering to SQL with NOT IN clauses, returning only
        stale entity IDs. Executes bulk deletes inline instead of generating
        individual Delete/Deactivate ops.

        Deletion strategy per entity type:
        - Workflows, Forms, Agents, Apps: hard-delete (existing behavior)
        - Integrations, Configs, Events: hard-delete (manifest is source of truth)
        - Tables: soft-delete (keep data, set inactive — never created here currently)
        - Knowledge: not managed by git-sync (ephemeral, derived from documents)
        - Organizations, Roles: soft-delete (only git-sync created ones)

        Returns list of EntityChange entries for removed entities.
        """
        from uuid import UUID

        from sqlalchemy import delete as sa_delete
        from sqlalchemy import update as sa_update

        from src.models.contracts.github import EntityChange
        from src.models.orm.agents import Agent
        from src.models.orm.applications import Application
        from src.models.orm.config import Config
        from src.models.orm.events import EventSource, EventSubscription
        from src.models.orm.forms import Form
        from src.models.orm.integrations import Integration
        from src.models.orm.organizations import Organization
        from src.models.orm.tables import Table
        from src.models.orm.users import Role
        from src.models.orm.workflows import Workflow

        if manifest is None:
            if work_dir:
                manifest = read_manifest_from_dir(work_dir / ".bifrost")
            else:
                raise ValueError("Either manifest or work_dir must be provided")

        # Build existence-check helpers based on repo or work_dir
        if repo:
            all_s3_paths = set(await repo.list(""))

            def _path_exists(p: str) -> bool:
                return p in all_s3_paths

            def _dir_exists(p: str) -> bool:
                prefix = p.rstrip("/") + "/"
                return any(sp.startswith(prefix) for sp in all_s3_paths)
        elif work_dir:
            def _path_exists(p: str) -> bool:
                return (work_dir / p).exists()

            def _dir_exists(p: str) -> bool:
                return (work_dir / p).is_dir()
        else:
            def _path_exists(p: str) -> bool:
                return True

            def _dir_exists(p: str) -> bool:
                return True

        # Collect UUIDs of entities present in the manifest AND whose files exist
        present_wf_uuids = [
            UUID(mwf.id) for mwf in manifest.workflows.values()
            if _path_exists(mwf.path)
        ]
        present_form_uuids = [
            UUID(mform.id) for mform in manifest.forms.values()
            if _path_exists(mform.path)
        ]
        present_agent_uuids = [
            UUID(magent.id) for magent in manifest.agents.values()
            if _path_exists(magent.path)
        ]
        present_app_uuids = [
            UUID(mapp.id) for mapp in manifest.apps.values()
            if _dir_exists(mapp.path)
        ]

        present_integ_uuids = [UUID(m.id) for m in manifest.integrations.values()]
        present_config_uuids = [UUID(m.id) for m in manifest.configs.values()]
        present_table_uuids = [UUID(m.id) for m in manifest.tables.values()]
        present_event_uuids = [UUID(m.id) for m in manifest.events.values()]
        present_sub_uuids: list[UUID] = []
        for mes in manifest.events.values():
            for msub in mes.subscriptions:
                present_sub_uuids.append(UUID(msub.id))
        present_org_uuids = [UUID(m.id) for m in manifest.organizations]
        present_role_uuids = [UUID(m.id) for m in manifest.roles]

        entity_changes: list[EntityChange] = []
        now = datetime.now(timezone.utc)

        # Helper: query stale IDs (+ names when available) and bulk-delete
        async def _bulk_delete(model: type, base_filter: list, present: list[UUID], entity_type: str) -> int:
            """Find IDs not in present list and delete them. Returns count."""
            has_name = "name" in model.__table__.columns  # type: ignore[attr-defined]
            if has_name:
                q = select(model.id, model.name).where(*base_filter)  # type: ignore[attr-defined]
            else:
                q = select(model.id).where(*base_filter)  # type: ignore[attr-defined]
            if present:
                q = q.where(model.id.notin_(present))  # type: ignore[attr-defined]
            result = await self.db.execute(q)
            rows = result.all()
            if not rows:
                return 0
            stale_ids = []
            for row in rows:
                sid = row[0]
                name = row[1] if has_name else str(sid)
                stale_ids.append(sid)
                logger.info(f"Deleting {model.__tablename__} {sid} ({name}) — removed from repo")  # type: ignore[attr-defined]
                entity_changes.append(EntityChange(
                    action="removed",
                    entity_type=entity_type,
                    name=name,
                ))
            if not dry_run:
                await self.db.execute(
                    sa_delete(model).where(model.id.in_(stale_ids))  # type: ignore[attr-defined]
                )
            return len(stale_ids)

        # Helper: query stale IDs and soft-delete (deactivate)
        async def _bulk_deactivate(model: type, base_filter: list, present: list[UUID], entity_type: str) -> int:
            has_name = "name" in model.__table__.columns  # type: ignore[attr-defined]
            if has_name:
                q = select(model.id, model.name).where(*base_filter)  # type: ignore[attr-defined]
            else:
                q = select(model.id).where(*base_filter)  # type: ignore[attr-defined]
            if present:
                q = q.where(model.id.notin_(present))  # type: ignore[attr-defined]
            result = await self.db.execute(q)
            rows = result.all()
            if not rows:
                return 0
            stale_ids = []
            for row in rows:
                sid = row[0]
                name = row[1] if has_name else str(sid)
                stale_ids.append(sid)
                logger.info(f"Deactivating {model.__tablename__} {sid} ({name}) — removed from manifest")  # type: ignore[attr-defined]
                entity_changes.append(EntityChange(
                    action="removed",
                    entity_type=entity_type,
                    name=name,
                ))
            if not dry_run:
                await self.db.execute(
                    sa_update(model)
                    .where(model.id.in_(stale_ids))  # type: ignore[attr-defined]
                    .values(is_active=False, updated_at=now)
                )
            return len(stale_ids)

        # Delete workflows synced from git that are no longer present
        await _bulk_delete(
            Workflow,
            [Workflow.is_active == True, Workflow.path.isnot(None)],  # noqa: E712
            present_wf_uuids,
            "workflows",
        )

        # Delete integrations not in manifest
        await _bulk_delete(
            Integration,
            [Integration.is_deleted == False],  # noqa: E712
            present_integ_uuids,
            "integrations",
        )

        # Delete configs not in manifest (skip integration-schema-linked configs —
        # those are user-set values managed by IntegrationConfigSchema cascade)
        cfg_q = select(Config.id).where(Config.config_schema_id.is_(None))
        if present_config_uuids:
            cfg_q = cfg_q.where(Config.id.notin_(present_config_uuids))
        cfg_result = await self.db.execute(cfg_q)
        stale_cfg_ids = [row[0] for row in cfg_result.all()]
        if stale_cfg_ids:
            for sid in stale_cfg_ids:
                logger.info(f"Deleting config {sid} — removed from repo")
                entity_changes.append(EntityChange(
                    action="removed",
                    entity_type="configs",
                    name=str(sid),
                ))
            if not dry_run:
                await self.db.execute(
                    sa_delete(Config).where(Config.id.in_(stale_cfg_ids))
                )

        # Tables not in manifest (data preserved — report as "keep")
        table_q = select(Table.id, Table.name)
        if present_table_uuids:
            table_q = table_q.where(Table.id.notin_(present_table_uuids))
        table_result = await self.db.execute(table_q)
        for row in table_result.all():
            logger.info(f"Table {row[0]} ({row[1]}) not in manifest (data preserved)")
            entity_changes.append(EntityChange(
                action="keep",
                entity_type="tables",
                name=row[1] or str(row[0]),
            ))

        # Delete event subscriptions not in manifest
        await _bulk_delete(EventSubscription, [], present_sub_uuids, "event_subscriptions")

        # Delete event sources not in manifest
        await _bulk_delete(EventSource, [], present_event_uuids, "events")

        # Delete forms not in manifest
        await _bulk_delete(
            Form,
            [Form.is_active == True],  # noqa: E712
            present_form_uuids,
            "forms",
        )

        # Delete agents not in manifest
        await _bulk_delete(Agent, [], present_agent_uuids, "agents")

        # Delete apps not in manifest
        await _bulk_delete(Application, [], present_app_uuids, "applications")

        # Soft-delete organizations not in manifest (only when manifest has orgs)
        if present_org_uuids:
            await _bulk_deactivate(
                Organization,
                [Organization.is_active == True],  # noqa: E712
                present_org_uuids,
                "organizations",
            )

        # Soft-delete roles not in manifest (only when manifest has roles)
        if present_role_uuids:
            await _bulk_deactivate(
                Role,
                [Role.is_active == True],  # noqa: E712
                present_role_uuids,
                "roles",
            )

        return entity_changes

    async def _detect_stale_entities(self, work_dir: Path | None = None, manifest: "Manifest | None" = None, repo: "RepoStorage | None" = None) -> list:
        """Read-only detection of entities that would be deleted during sync.

        Same logic as _resolve_deletions but only queries — no deletes or updates.
        Returns list of EntityChange entries for entities that are stale.
        """
        from uuid import UUID

        from src.models.contracts.github import EntityChange
        from src.models.orm.agents import Agent
        from src.models.orm.applications import Application
        from src.models.orm.config import Config
        from src.models.orm.events import EventSource, EventSubscription
        from src.models.orm.forms import Form
        from src.models.orm.integrations import Integration
        from src.models.orm.organizations import Organization
        from src.models.orm.users import Role
        from src.models.orm.workflows import Workflow

        if manifest is None:
            if work_dir:
                manifest = read_manifest_from_dir(work_dir / ".bifrost")
            else:
                raise ValueError("Either manifest or work_dir must be provided")

        # Build existence-check helpers based on repo or work_dir
        if repo:
            all_s3_paths = set(await repo.list(""))

            def _path_exists(p: str) -> bool:
                return p in all_s3_paths

            def _dir_exists(p: str) -> bool:
                prefix = p.rstrip("/") + "/"
                return any(sp.startswith(prefix) for sp in all_s3_paths)
        elif work_dir:
            def _path_exists(p: str) -> bool:
                return (work_dir / p).exists()

            def _dir_exists(p: str) -> bool:
                return (work_dir / p).is_dir()
        else:
            def _path_exists(p: str) -> bool:
                return True

            def _dir_exists(p: str) -> bool:
                return True

        present_wf_uuids = [
            UUID(mwf.id) for mwf in manifest.workflows.values()
            if _path_exists(mwf.path)
        ]
        present_form_uuids = [
            UUID(mform.id) for mform in manifest.forms.values()
            if _path_exists(mform.path)
        ]
        present_agent_uuids = [
            UUID(magent.id) for magent in manifest.agents.values()
            if _path_exists(magent.path)
        ]
        present_app_uuids = [
            UUID(mapp.id) for mapp in manifest.apps.values()
            if _dir_exists(mapp.path)
        ]
        present_integ_uuids = [UUID(m.id) for m in manifest.integrations.values()]
        present_config_uuids = [UUID(m.id) for m in manifest.configs.values()]
        present_event_uuids = [UUID(m.id) for m in manifest.events.values()]
        present_sub_uuids: list[UUID] = []
        for mes in manifest.events.values():
            for msub in mes.subscriptions:
                present_sub_uuids.append(UUID(msub.id))
        present_org_uuids = [UUID(m.id) for m in manifest.organizations]
        present_role_uuids = [UUID(m.id) for m in manifest.roles]

        entity_changes: list[EntityChange] = []

        async def _detect_stale(model: type, base_filter: list, present: list[UUID], entity_type: str) -> None:
            """Query stale IDs without deleting."""
            has_name = "name" in model.__table__.columns  # type: ignore[attr-defined]
            if has_name:
                q = select(model.id, model.name).where(*base_filter)  # type: ignore[attr-defined]
            else:
                q = select(model.id).where(*base_filter)  # type: ignore[attr-defined]
            if present:
                q = q.where(model.id.notin_(present))  # type: ignore[attr-defined]
            result = await self.db.execute(q)
            for row in result.all():
                name = row[1] if has_name else str(row[0])
                entity_changes.append(EntityChange(
                    action="removed",
                    entity_type=entity_type,
                    name=name,
                ))

        await _detect_stale(
            Workflow,
            [Workflow.is_active == True, Workflow.path.isnot(None)],  # noqa: E712
            present_wf_uuids, "workflows",
        )
        await _detect_stale(
            Integration,
            [Integration.is_deleted == False],  # noqa: E712
            present_integ_uuids, "integrations",
        )

        # Configs (skip integration-schema-linked configs)
        cfg_q = select(Config.id).where(Config.config_schema_id.is_(None))
        if present_config_uuids:
            cfg_q = cfg_q.where(Config.id.notin_(present_config_uuids))
        cfg_result = await self.db.execute(cfg_q)
        for row in cfg_result.all():
            entity_changes.append(EntityChange(
                action="removed", entity_type="configs", name=str(row[0]),
            ))

        await _detect_stale(EventSubscription, [], present_sub_uuids, "event_subscriptions")
        await _detect_stale(EventSource, [], present_event_uuids, "events")
        await _detect_stale(
            Form,
            [Form.is_active == True],  # noqa: E712
            present_form_uuids, "forms",
        )
        await _detect_stale(Agent, [], present_agent_uuids, "agents")
        await _detect_stale(Application, [], present_app_uuids, "applications")

        if present_org_uuids:
            await _detect_stale(
                Organization,
                [Organization.is_active == True],  # noqa: E712
                present_org_uuids, "organizations",
            )
        if present_role_uuids:
            await _detect_stale(
                Role,
                [Role.is_active == True],  # noqa: E712
                present_role_uuids, "roles",
            )

        return entity_changes

    async def _resolve_integration(self, integ_name: str, minteg, cache: dict | None = None) -> "list[SyncOp]":
        """Resolve an integration from manifest into SyncOps.

        Upserts the integration and directly executes config schema, oauth
        provider, and mapping sub-operations (these are complex sub-object
        syncs without their own resolution pattern).
        Uses prefetch cache for lookups when available.
        """
        from uuid import UUID

        from sqlalchemy.dialects.postgresql import insert

        from src.models.orm.integrations import Integration, IntegrationConfigSchema, IntegrationMapping
        from src.models.orm.oauth import OAuthProvider
        from src.services.sync_ops import SyncOp, Upsert  # noqa: F401

        integ_id = UUID(minteg.id)

        # Check by natural key (name) — use cache if available
        if cache is not None:
            existing_by_name = cache["integ_by_name"].get(integ_name)
        else:
            by_name = await self.db.execute(
                select(Integration.id).where(Integration.name == integ_name)
            )
            existing_by_name = by_name.scalar_one_or_none()

        integ_values: dict = {
            "name": integ_name,
            "entity_id": minteg.entity_id,
            "entity_id_name": minteg.entity_id_name,
            "default_entity_id": minteg.default_entity_id,
            "list_entities_data_provider_id": (
                UUID(minteg.list_entities_data_provider_id)
                if minteg.list_entities_data_provider_id else None
            ),
            "is_deleted": False,
        }

        # Upsert integration row FIRST (must exist before config schema / mapping FKs)
        if existing_by_name is not None:
            upsert_op = Upsert(
                model=Integration,
                id=existing_by_name,
                values={"id": integ_id, **integ_values},
                match_on="id",
            )
        else:
            upsert_op = Upsert(
                model=Integration,
                id=integ_id,
                values=integ_values,
                match_on="id",
            )
        await upsert_op.execute(self.db)

        # Sync config schema items: upsert by (integration_id, key) to preserve IDs
        # (Config rows reference schema IDs via FK — deleting schema cascades to configs)
        from sqlalchemy import delete as sa_delete
        if cache is not None:
            existing_cs_by_key = dict(cache["integ_cs"].get(integ_id, {}))
        else:
            existing_cs_result = await self.db.execute(
                select(IntegrationConfigSchema).where(
                    IntegrationConfigSchema.integration_id == integ_id
                )
            )
            existing_cs_by_key = {cs.key: cs for cs in existing_cs_result.scalars().all()}
        manifest_cs_keys = {cs.key for cs in minteg.config_schema}

        for cs in minteg.config_schema:
            if cs.key in existing_cs_by_key:
                existing_cs = existing_cs_by_key[cs.key]
                existing_cs.type = cs.type
                existing_cs.required = cs.required
                existing_cs.description = cs.description
                existing_cs.options = cs.options
                existing_cs.position = cs.position
            else:
                cs_stmt = insert(IntegrationConfigSchema).values(
                    integration_id=integ_id,
                    key=cs.key,
                    type=cs.type,
                    required=cs.required,
                    description=cs.description,
                    options=cs.options,
                    position=cs.position,
                )
                await self.db.execute(cs_stmt)

        removed_keys = set(existing_cs_by_key.keys()) - manifest_cs_keys
        if removed_keys:
            await self.db.execute(
                sa_delete(IntegrationConfigSchema).where(
                    IntegrationConfigSchema.integration_id == integ_id,
                    IntegrationConfigSchema.key.in_(removed_keys),
                )
            )

        # Sync OAuth provider (structure only — client_secret never imported)
        if minteg.oauth_provider:
            op_data = minteg.oauth_provider
            op_stmt = insert(OAuthProvider).values(
                provider_name=op_data.provider_name,
                display_name=op_data.display_name,
                oauth_flow_type=op_data.oauth_flow_type,
                client_id=op_data.client_id,
                encrypted_client_secret=b"",  # placeholder — needs manual setup
                authorization_url=op_data.authorization_url,
                token_url=op_data.token_url,
                token_url_defaults=op_data.token_url_defaults or {},
                scopes=op_data.scopes or [],
                redirect_uri=op_data.redirect_uri,
                integration_id=integ_id,
            ).on_conflict_do_update(
                constraint="uq_oauth_providers_integration_id",
                set_={
                    "display_name": op_data.display_name,
                    "oauth_flow_type": op_data.oauth_flow_type,
                    **(
                        {"client_id": op_data.client_id}
                        if op_data.client_id and op_data.client_id != "__NEEDS_SETUP__"
                        else {}
                    ),
                    "authorization_url": op_data.authorization_url,
                    "token_url": op_data.token_url,
                    "token_url_defaults": op_data.token_url_defaults or {},
                    "scopes": op_data.scopes or [],
                    "redirect_uri": op_data.redirect_uri,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            await self.db.execute(op_stmt)

        # Sync mappings: upsert by (integration_id, organization_id) to preserve oauth_token_id
        if cache is not None:
            existing_m_by_org: dict[str | None, IntegrationMapping] = dict(cache["integ_mappings"].get(integ_id, {}))
        else:
            existing_m_result = await self.db.execute(
                select(IntegrationMapping).where(
                    IntegrationMapping.integration_id == integ_id
                )
            )
            existing_m_by_org = {
                str(m.organization_id) if m.organization_id else None: m
                for m in existing_m_result.scalars().all()
            }
        manifest_org_ids = {mapping.organization_id for mapping in minteg.mappings}

        for mapping in minteg.mappings:
            org_key = mapping.organization_id  # str or None
            if org_key in existing_m_by_org:
                existing_m = existing_m_by_org[org_key]
                existing_m.entity_id = mapping.entity_id
                existing_m.entity_name = mapping.entity_name
                if mapping.oauth_token_id is not None:
                    existing_m.oauth_token_id = UUID(mapping.oauth_token_id)
            else:
                m_stmt = insert(IntegrationMapping).values(
                    integration_id=integ_id,
                    organization_id=UUID(mapping.organization_id) if mapping.organization_id else None,
                    entity_id=mapping.entity_id,
                    entity_name=mapping.entity_name,
                    oauth_token_id=UUID(mapping.oauth_token_id) if mapping.oauth_token_id else None,
                )
                await self.db.execute(m_stmt)

        for org_key, existing_m in existing_m_by_org.items():
            if org_key not in manifest_org_ids:
                await self.db.execute(
                    sa_delete(IntegrationMapping).where(
                        IntegrationMapping.id == existing_m.id
                    )
                )

        # Return empty list — all operations executed directly above
        return []

    def _resolve_config(self, mcfg, cache: dict) -> "list[SyncOp]":
        """Resolve a config entry from manifest into SyncOps.

        Uses prefetch cache for lookup. Skips writing value if type=SECRET
        and existing value is non-null. Returns ops list.
        """
        from uuid import UUID

        from src.models.orm.config import Config
        from src.services.sync_ops import SyncOp, Upsert  # noqa: F401

        cfg_id = UUID(mcfg.id)
        integ_id = UUID(mcfg.integration_id) if mcfg.integration_id else None
        org_id = UUID(mcfg.organization_id) if mcfg.organization_id else None

        # Check prefetch cache for existing config by natural key
        cache_hit = cache["config_by_natural"].get((mcfg.key, integ_id, org_id))

        if cache_hit is not None:
            existing_id, existing_value, _config_schema_id = cache_hit

            # Secret with existing value — don't overwrite
            if mcfg.config_type == "secret" and existing_value is not None:
                return []

            # Update existing row (including ID if it changed)
            update_values: dict = {
                "id": cfg_id,
                "key": mcfg.key,
                "config_type": mcfg.config_type,
                "description": mcfg.description,
                "integration_id": integ_id,
                "organization_id": org_id,
                "updated_by": "git-sync",
            }
            if mcfg.config_type != "secret":
                update_values["value"] = mcfg.value if mcfg.value is not None else {}

            return [Upsert(
                model=Config,
                id=existing_id,
                values=update_values,
                match_on="id",
            )]
        else:
            # New config — return Upsert op (uses ON CONFLICT)
            insert_values: dict = {
                "key": mcfg.key,
                "config_type": mcfg.config_type,
                "description": mcfg.description,
                "integration_id": integ_id,
                "organization_id": org_id,
                "value": mcfg.value if mcfg.value is not None else {},
                "updated_by": "git-sync",
            }
            return [Upsert(
                model=Config,
                id=cfg_id,
                values=insert_values,
                match_on="id",
            )]

    def _resolve_app(self, mapp, cache: dict) -> "list[SyncOp]":
        """Resolve an app from manifest into SyncOps (metadata only).
        Uses prefetch cache for slug lookup.
        """
        from pathlib import PurePosixPath
        from uuid import UUID

        from src.models.orm.app_roles import AppRole
        from src.models.orm.applications import Application
        from src.services.sync_ops import SyncOp, SyncRoles, Upsert  # noqa: F401

        # repo_path is now the directory directly (no /app.yaml to strip)
        repo_path = mapp.path.rstrip("/") if mapp.path else None

        # Slug from manifest entry, or derive from repo_path leaf
        slug = mapp.slug or (PurePosixPath(repo_path).name if repo_path else None)
        if not slug:
            logger.warning(f"App {mapp.id} has no slug or path, skipping")
            return []

        if not repo_path:
            repo_path = f"apps/{slug}"

        app_id = UUID(mapp.id)
        org_id = UUID(mapp.organization_id) if mapp.organization_id else None
        access_level = getattr(mapp, "access_level", "role_based")

        # Check prefetch cache for existing app by slug
        existing_id = cache["app_by_slug"].get(slug)

        app_values = {
            "name": mapp.name or "",
            "description": mapp.description,
            "slug": slug,
            "repo_path": repo_path,
            "organization_id": org_id,
            "access_level": access_level,
            "dependencies": mapp.dependencies or None,
        }

        ops: list[SyncOp] = []

        if existing_id is not None:
            ops.append(Upsert(
                model=Application,
                id=existing_id,
                values={"id": app_id, **app_values},
                match_on="id",
            ))
        else:
            ops.append(Upsert(
                model=Application,
                id=app_id,
                values=app_values,
                match_on="id",
            ))

        # Role sync op
        if hasattr(mapp, "roles") and mapp.roles:
            role_ids = {UUID(r) for r in mapp.roles}
            ops.append(SyncRoles(
                junction_model=AppRole,
                entity_fk="app_id",
                entity_id=app_id,
                role_ids=role_ids,
            ))

        return ops

    async def _resolve_table(self, table_name: str, mtable, cache: dict | None = None) -> "list[SyncOp]":
        """Resolve a table definition from manifest into SyncOps (schema only, no data).

        Uses prefetch cache for lookups when available.
        Two-pass natural-key lookup (mirrors _resolve_workflow):
        1. Match by (name, organization_id) — if found, update including ID realignment
        2. Match by ID — if found, update name/schema
        3. Otherwise insert new

        ID realignment ensures the DB row ID matches the manifest UUID so that
        _resolve_deletions can correctly identify which tables are present.
        Documents are preserved in all cases (cascade is on the table row, and
        we never delete the row here).
        """
        from uuid import UUID

        from sqlalchemy import update
        from sqlalchemy.dialects.postgresql import insert

        from src.models.orm.tables import Table
        from src.services.sync_ops import SyncOp  # noqa: F401

        table_id = UUID(mtable.id)
        org_id = UUID(mtable.organization_id) if mtable.organization_id else None
        app_id = UUID(mtable.application_id) if mtable.application_id else None
        now = datetime.now(timezone.utc)

        # 1. Look up by natural key (name + org) — use cache if available
        if cache is not None:
            existing_by_natural = cache["table_by_natural"].get((table_name, org_id))
        else:
            natural_q = select(Table.id).where(
                Table.name == table_name,
                Table.organization_id == org_id,
            )
            existing_by_natural = (await self.db.execute(natural_q)).scalar_one_or_none()

        if existing_by_natural is not None:
            if existing_by_natural != table_id:
                # ID mismatch (cross-env) — realign the DB row's ID to the manifest ID.
                # Documents have ON UPDATE CASCADE on table_id so they follow along.
                logger.info(
                    f"Realigning table {table_name!r}: DB id={existing_by_natural} → manifest id={table_id}"
                )
            await self.db.execute(
                update(Table)
                .where(Table.id == existing_by_natural)
                .values(
                    id=table_id,
                    description=mtable.description,
                    application_id=app_id,
                    schema=mtable.table_schema,
                    updated_at=now,
                )
            )
            return []

        # 2. Look up by ID (name changed, same ID) — use cache if available
        if cache is not None:
            existing_by_id = table_id if table_id in cache["table_ids"] else None
        else:
            existing_by_id = (
                await self.db.execute(select(Table.id).where(Table.id == table_id))
            ).scalar_one_or_none()

        if existing_by_id is not None:
            await self.db.execute(
                update(Table)
                .where(Table.id == table_id)
                .values(
                    name=table_name,
                    description=mtable.description,
                    application_id=app_id,
                    schema=mtable.table_schema,
                    updated_at=now,
                )
            )
            return []

        # 3. New table — insert
        stmt = insert(Table).values(
            id=table_id,
            name=table_name,
            description=mtable.description,
            organization_id=org_id,
            application_id=app_id,
            schema=mtable.table_schema,
            created_by="git-sync",
        ).on_conflict_do_nothing()
        await self.db.execute(stmt)

        return []

    async def _resolve_event_source(self, es_name: str, mes, imported_wf_ids: set[str] | None = None) -> "list[SyncOp]":
        """Resolve an event source + subscriptions from manifest into SyncOps.

        Event sources use PostgreSQL ON CONFLICT upserts (PostgreSQL-specific
        constructs); executed directly here, returning empty ops list.

        imported_wf_ids: set of workflow UUIDs (as strings) that were actually
        imported (file existed on disk). Subscriptions referencing workflows
        not in this set are skipped to avoid FK violations.
        """
        from uuid import UUID

        from sqlalchemy.dialects.postgresql import insert

        from src.models.orm.events import EventSource, EventSubscription, ScheduleSource, WebhookSource
        from src.services.sync_ops import SyncOp  # noqa: F401

        es_id = UUID(mes.id)

        # Upsert event source
        stmt = insert(EventSource).values(
            id=es_id,
            name=es_name,
            source_type=mes.source_type,
            organization_id=UUID(mes.organization_id) if mes.organization_id else None,
            is_active=mes.is_active,
            created_by="git-sync",
        ).on_conflict_do_update(
            index_elements=["id"],
            set_={
                "name": es_name,
                "source_type": mes.source_type,
                "organization_id": UUID(mes.organization_id) if mes.organization_id else None,
                "is_active": mes.is_active,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        await self.db.execute(stmt)

        # Upsert schedule source if applicable
        if mes.source_type == "schedule" and mes.cron_expression:
            sched_stmt = insert(ScheduleSource).values(
                event_source_id=es_id,
                cron_expression=mes.cron_expression,
                timezone=mes.timezone or "UTC",
                enabled=mes.schedule_enabled if mes.schedule_enabled is not None else True,
            ).on_conflict_do_update(
                index_elements=["event_source_id"],
                set_={
                    "cron_expression": mes.cron_expression,
                    "timezone": mes.timezone or "UTC",
                    "enabled": mes.schedule_enabled if mes.schedule_enabled is not None else True,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            await self.db.execute(sched_stmt)

        # Upsert webhook source if applicable (external state left empty)
        if mes.source_type == "webhook":
            wh_stmt = insert(WebhookSource).values(
                event_source_id=es_id,
                adapter_name=mes.adapter_name,
                integration_id=UUID(mes.webhook_integration_id) if mes.webhook_integration_id else None,
                config=mes.webhook_config or {},
            ).on_conflict_do_update(
                index_elements=["event_source_id"],
                set_={
                    "adapter_name": mes.adapter_name,
                    "integration_id": UUID(mes.webhook_integration_id) if mes.webhook_integration_id else None,
                    "config": mes.webhook_config or {},
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            await self.db.execute(wh_stmt)

        # Sync subscriptions: upsert each
        # workflow_id may be a UUID string, a path::function_name portable ref, or a name
        for msub in mes.subscriptions:
            target_type = getattr(msub, "target_type", "workflow") or "workflow"

            wf_id: UUID | None = None
            agent_id: UUID | None = None

            if target_type == "agent":
                # Agent-targeted subscription
                if msub.agent_id:
                    try:
                        agent_id = UUID(msub.agent_id)
                    except ValueError:
                        logger.warning(
                            f"Event subscription {msub.id}: invalid agent_id "
                            f"'{msub.agent_id}', skipping"
                        )
                        continue
                else:
                    logger.warning(
                        f"Event subscription {msub.id}: target_type='agent' but "
                        f"no agent_id, skipping"
                    )
                    continue
            else:
                # Workflow-targeted subscription
                try:
                    wf_id = UUID(msub.workflow_id) if msub.workflow_id else None
                except (ValueError, AttributeError):
                    pass

                # For UUID workflow refs: skip if that workflow wasn't imported
                if wf_id is not None and imported_wf_ids is not None and msub.workflow_id not in imported_wf_ids:
                    logger.warning(
                        f"Event subscription {msub.id}: workflow {msub.workflow_id} "
                        f"not imported (file missing?), skipping"
                    )
                    continue

                if wf_id is None and msub.workflow_id:
                    # Try path::function_name or name resolution
                    resolved = await self._resolve_workflow_ref(msub.workflow_id)
                    if resolved is None:
                        logger.warning(
                            f"Event subscription {msub.id}: could not resolve workflow ref "
                            f"'{msub.workflow_id}', skipping"
                        )
                        continue
                    wf_id = resolved

                if wf_id is None:
                    logger.warning(
                        f"Event subscription {msub.id}: target_type='workflow' but "
                        f"no workflow_id, skipping"
                    )
                    continue

            sub_stmt = insert(EventSubscription).values(
                id=UUID(msub.id),
                event_source_id=es_id,
                target_type=target_type,
                workflow_id=wf_id,
                agent_id=agent_id,
                event_type=msub.event_type,
                filter_expression=msub.filter_expression,
                input_mapping=msub.input_mapping,
                is_active=msub.is_active,
                created_by="git-sync",
            ).on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "event_source_id": es_id,
                    "target_type": target_type,
                    "workflow_id": wf_id,
                    "agent_id": agent_id,
                    "event_type": msub.event_type,
                    "filter_expression": msub.filter_expression,
                    "input_mapping": msub.input_mapping,
                    "is_active": msub.is_active,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            await self.db.execute(sub_stmt)

        return []

    def _resolve_form(self, mform, content: bytes) -> "list[SyncOp]":
        """Resolve form metadata from manifest into SyncOps.

        The FormIndexer call (content parsing) is a side-effect performed in
        _import_all_entities, not here. This method only handles metadata ops.
        """
        from uuid import UUID

        from src.models.orm.forms import Form, FormRole
        from src.services.sync_ops import SyncOp, SyncRoles, Upsert  # noqa: F401

        data = yaml.safe_load(content.decode("utf-8"))
        if not data:
            return []

        org_id = UUID(mform.organization_id) if mform.organization_id else None
        form_id = UUID(mform.id)
        ops: list[SyncOp] = []

        if org_id:
            form_values: dict = {
                "name": data.get("name", ""),
                "is_active": True,
                "created_by": "git-sync",
                "organization_id": org_id,
            }
            if hasattr(mform, "access_level") and mform.access_level:
                form_values["access_level"] = mform.access_level
            ops.append(Upsert(
                model=Form,
                id=form_id,
                values=form_values,
                match_on="id",
            ))

        # Role sync op (FormRole.assigned_by is NOT NULL — pass via extra_fields)
        if hasattr(mform, "roles") and mform.roles:
            role_ids = {UUID(r) for r in mform.roles}
            ops.append(SyncRoles(
                junction_model=FormRole,
                entity_fk="form_id",
                entity_id=form_id,
                role_ids=role_ids,
                extra_fields={"assigned_by": "git-sync"},
            ))

        return ops

    def _resolve_agent(self, magent, content: bytes) -> "list[SyncOp]":
        """Resolve agent metadata from manifest into SyncOps.

        The AgentIndexer call (content parsing) is a side-effect performed in
        _import_all_entities, not here. This method only handles metadata ops.
        """
        from uuid import UUID

        from src.models.orm.agents import Agent, AgentRole
        from src.services.sync_ops import SyncOp, SyncRoles, Upsert  # noqa: F401

        data = yaml.safe_load(content.decode("utf-8"))
        if not data:
            return []

        org_id = UUID(magent.organization_id) if magent.organization_id else None
        agent_id = UUID(magent.id)
        ops: list[SyncOp] = []

        if org_id:
            agent_values: dict = {
                "name": data.get("name", ""),
                "system_prompt": data.get("system_prompt", ""),
                "is_active": True,
                "created_by": "git-sync",
                "organization_id": org_id,
                "max_iterations": data.get("max_iterations"),
                "max_token_budget": data.get("max_token_budget"),
            }
            if hasattr(magent, "access_level") and magent.access_level:
                agent_values["access_level"] = magent.access_level
            ops.append(Upsert(
                model=Agent,
                id=agent_id,
                values=agent_values,
                match_on="id",
            ))

        # Role sync op (AgentRole.assigned_by is NOT NULL — pass via extra_fields)
        if hasattr(magent, "roles") and magent.roles:
            role_ids = {UUID(r) for r in magent.roles}
            ops.append(SyncRoles(
                junction_model=AgentRole,
                entity_fk="agent_id",
                entity_id=agent_id,
                role_ids=role_ids,
                extra_fields={"assigned_by": "git-sync"},
            ))

        return ops

    async def _update_file_index(self, work_dir: Path) -> None:
        """Update file_index from all files in the working tree, remove stale entries.

        Optimized: prefetches existing (path, content_hash) pairs in one query,
        skips files whose hash hasn't changed, and batch-upserts the rest in
        chunks of 100.
        """
        from sqlalchemy import delete, text
        from sqlalchemy.dialects.postgresql import insert

        from src.models.orm.file_index import FileIndex
        from src.services.file_index_service import _is_text_file

        files = _walk_tree(work_dir)
        repo_paths = set(files.keys())

        # Prefetch all existing (path, content_hash) in one query
        existing_result = await self.db.execute(
            select(FileIndex.path, FileIndex.content_hash)
        )
        existing_hashes = {row[0]: row[1] for row in existing_result.all()}

        # Build list of rows that need upserting (changed or new)
        pending_upserts: list[dict] = []
        for rel_path, content in files.items():
            if not _is_text_file(rel_path):
                continue
            try:
                content_str = content.decode("utf-8")
            except UnicodeDecodeError:
                continue
            content_hash = _content_hash(content)

            # Skip if hash hasn't changed
            if existing_hashes.get(rel_path) == content_hash:
                continue

            pending_upserts.append({
                "path": rel_path,
                "content": content_str,
                "content_hash": content_hash,
            })

        # Batch upsert in chunks of 100
        CHUNK_SIZE = 100
        for i in range(0, len(pending_upserts), CHUNK_SIZE):
            chunk = pending_upserts[i : i + CHUNK_SIZE]
            stmt = insert(FileIndex).values(chunk).on_conflict_do_update(
                index_elements=[FileIndex.path],
                set_={
                    "content": insert(FileIndex).excluded.content,
                    "content_hash": insert(FileIndex).excluded.content_hash,
                    "updated_at": text("NOW()"),
                },
            )
            await self.db.execute(stmt)

        if pending_upserts:
            logger.info(f"File index: upserted {len(pending_upserts)} changed files, skipped {len(files) - len(pending_upserts)} unchanged")

        # Remove file_index entries that no longer exist in the repo
        stale_paths = set(existing_hashes.keys()) - repo_paths
        if stale_paths:
            await self.db.execute(
                delete(FileIndex).where(FileIndex.path.in_(stale_paths))
            )

    # -----------------------------------------------------------------
    # Internal: preflight validation
    # -----------------------------------------------------------------

    async def _run_preflight(self, repo_dir: Path) -> PreflightResult:
        """Run all preflight checks against a repo directory."""
        issues: list[PreflightIssue] = []

        # 1. Check manifest validity
        bifrost_dir = repo_dir / ".bifrost"
        manifest: Manifest | None = None
        if bifrost_dir.exists():
            try:
                manifest = read_manifest_from_dir(bifrost_dir)
                # Verify all paths exist
                from src.services.manifest import get_all_paths
                for path in get_all_paths(manifest):
                    if not (repo_dir / path).exists():
                        issues.append(PreflightIssue(
                            path=".bifrost/",
                            message=f"Manifest references missing file: {path}",
                            severity="error",
                            category="manifest",
                            fix_hint="This file was deleted but the entity is still registered. Use 'Clean up & Retry' to remove orphaned references.",
                            auto_fixable=True,
                        ))
            except Exception as e:
                issues.append(PreflightIssue(
                    path=".bifrost/",
                    message=f"Invalid manifest: {e}",
                    severity="error",
                    category="manifest",
                    fix_hint="The manifest is malformed. Run 'Reimport' from Settings > Maintenance.",
                ))

        # 2. Syntax check all .py files
        for py_file in repo_dir.rglob("*.py"):
            rel = str(py_file.relative_to(repo_dir))
            if rel.startswith(".git/"):
                continue
            try:
                source = py_file.read_text()
                compile(source, rel, "exec")
            except SyntaxError as e:
                issues.append(PreflightIssue(
                    path=rel,
                    line=e.lineno,
                    message=f"Syntax error: {e.msg}",
                    severity="error",
                    category="syntax",
                    fix_hint=f"Fix the syntax error in {rel} at line {e.lineno}.",
                ))

        # 3. Ruff lint check
        py_files = [
            str(f) for f in repo_dir.rglob("*.py")
            if not str(f.relative_to(repo_dir)).startswith(".git/")
        ]
        if py_files:
            try:
                result = subprocess.run(
                    ["ruff", "check", "--output-format=json", "--no-fix", *py_files],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    cwd=str(repo_dir),
                )
                if result.stdout.strip():
                    import json
                    for violation in json.loads(result.stdout):
                        rel_path = str(Path(violation["filename"]).relative_to(repo_dir))
                        issues.append(PreflightIssue(
                            path=rel_path,
                            line=violation.get("location", {}).get("row"),
                            message=f"{violation.get('code', '?')}: {violation.get('message', '')}",
                            severity="warning",
                            category="lint",
                            fix_hint="This is a style warning and won't block your commit.",
                        ))
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass  # ruff not available or timed out — skip lint

        # 4. Ref resolution (UUID references in entity files)
        if manifest:
            entity_ids = get_all_entity_ids(manifest)
            # Check forms for workflow UUID references
            for form_name, mform in manifest.forms.items():
                form_path = repo_dir / mform.path
                if form_path.exists():
                    try:
                        data = yaml.safe_load(form_path.read_text())
                        if data:
                            wf_ref = data.get("workflow")
                            if wf_ref and wf_ref not in entity_ids:
                                issues.append(PreflightIssue(
                                    path=mform.path,
                                    message=f"Form references unknown workflow UUID: {wf_ref}",
                                    severity="error",
                                    category="ref",
                                    fix_hint="Edit this form and assign a valid workflow.",
                                ))
                            launch_ref = data.get("launch_workflow")
                            if launch_ref and launch_ref not in entity_ids:
                                issues.append(PreflightIssue(
                                    path=mform.path,
                                    message=f"Form references unknown launch workflow UUID: {launch_ref}",
                                    severity="error",
                                    category="ref",
                                    fix_hint="Edit this form and assign a valid launch workflow.",
                                ))
                    except Exception:
                        pass

            # 5. Orphan detection — workflows referenced by forms but missing from manifest
            wf_ids = {mwf.id for mwf in manifest.workflows.values()}
            for form_name, mform in manifest.forms.items():
                form_path = repo_dir / mform.path
                if form_path.exists():
                    try:
                        data = yaml.safe_load(form_path.read_text())
                        if data:
                            wf_ref = data.get("workflow")
                            if wf_ref and wf_ref not in wf_ids:
                                issues.append(PreflightIssue(
                                    path=mform.path,
                                    message=f"Form '{form_name}' references workflow {wf_ref} which is not in the manifest (will be orphaned)",
                                    severity="warning",
                                    category="orphan",
                                    fix_hint="Register the referenced workflow, or update the form to reference an active one.",
                                ))
                    except Exception:
                        pass

            # 6. Cross-reference validation for new entity types
            from src.services.manifest import validate_manifest
            ref_errors = validate_manifest(manifest)
            for err in ref_errors:
                issues.append(PreflightIssue(
                    path=".bifrost/",
                    message=err,
                    severity="error",
                    category="ref",
                    fix_hint="Check that all referenced entity IDs exist and are active.",
                ))

            # 7. Health warnings (non-blocking)
            # Secret configs with null values
            for cfg_key, mcfg in manifest.configs.items():
                if mcfg.config_type == "secret" and mcfg.value is None:
                    issues.append(PreflightIssue(
                        path=".bifrost/configs.yaml",
                        message=f"Config '{cfg_key}' (type=secret) needs a value after import",
                        severity="warning",
                        category="health",
                        fix_hint="Set a value for this config in Settings > Integrations.",
                    ))

            # OAuth providers needing setup
            for integ_name, minteg in manifest.integrations.items():
                if minteg.oauth_provider and minteg.oauth_provider.client_id == "__NEEDS_SETUP__":
                    issues.append(PreflightIssue(
                        path=".bifrost/integrations.yaml",
                        message=f"Integration '{integ_name}' OAuth provider needs client_id and client_secret setup",
                        severity="warning",
                        category="health",
                        fix_hint="Configure OAuth client_id and client_secret in Settings > Integrations.",
                    ))

            # Webhook sources needing external registration
            for es_name, mes in manifest.events.items():
                if mes.source_type == "webhook":
                    issues.append(PreflightIssue(
                        path=".bifrost/events.yaml",
                        message=f"Webhook source '{es_name}' will need external registration after import",
                        severity="warning",
                        category="health",
                        fix_hint="Register this webhook URL with the external service after import.",
                    ))

        has_errors = any(i.severity == "error" for i in issues)
        return PreflightResult(valid=not has_errors, issues=issues)
