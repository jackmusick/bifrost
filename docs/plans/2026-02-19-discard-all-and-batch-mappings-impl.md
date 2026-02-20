# Discard All + Batch Mapping Save Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a right-click "Discard All Changes" context menu to source control, and a batch mapping save endpoint to eliminate N individual API calls.

**Architecture:** Two independent features. Feature 1 is frontend-only (context menu + AlertDialog on the Changes header). Feature 2 adds a new batch endpoint `POST /integrations/{id}/mappings/batch` and rewrites the frontend `handleSaveAll` to use it.

**Tech Stack:** React (shadcn ContextMenu + AlertDialog), FastAPI, SQLAlchemy, openapi-react-query

---

### Task 1: Discard All — Context Menu on Changes Header

**Files:**
- Modify: `client/src/components/editor/SourceControlPanel.tsx`

**Step 1: Add `onDiscardAll` prop and state to ChangesSection**

Add a new prop `onDiscardAll` to `ChangesSection` and a state for the confirmation dialog. In the parent component, add the handler that calls `discardOp.mutateAsync` with all file paths.

In the parent (around line 606, after `handleDiscard`), add:

```typescript
const handleDiscardAll = useCallback(async () => {
	if (changedFiles.length === 0) return;
	try {
		const result = await runGitOp<DiscardResult>(
			() => discardOp.mutateAsync(changedFiles.map((f) => f.path)),
			"discard",
		);
		if (result.success) {
			toast.success(`Discarded all ${changedFiles.length} changes`);
			setChangedFiles([]);
			refreshStatus();
		} else {
			toast.error(result.error || "Discard all failed");
		}
	} catch (error) {
		if (error instanceof Error) {
			toast.error(error.message);
		}
	}
}, [changedFiles, discardOp, runGitOp, refreshStatus]);
```

Pass `onDiscardAll={handleDiscardAll}` to `ChangesSection`.

**Step 2: Add context menu and confirmation dialog to ChangesSection**

Add imports at top of file:
```typescript
import {
	ContextMenu,
	ContextMenuContent,
	ContextMenuItem,
	ContextMenuTrigger,
} from "@/components/ui/context-menu";
import {
	AlertDialog,
	AlertDialogAction,
	AlertDialogCancel,
	AlertDialogContent,
	AlertDialogDescription,
	AlertDialogFooter,
	AlertDialogHeader,
	AlertDialogTitle,
} from "@/components/ui/alert-dialog";
```

In `ChangesSection`, add the `onDiscardAll` prop to the type signature, add state:
```typescript
const [showDiscardAllConfirm, setShowDiscardAllConfirm] = useState(false);
```

Wrap the existing `<button>` header (the expand/collapse toggle, lines 990-1004) with `ContextMenu`:

```tsx
<ContextMenu>
	<ContextMenuTrigger asChild>
		<button
			onClick={() => setExpanded(!expanded)}
			className="w-full px-4 py-2 flex items-center gap-2 hover:bg-muted/30 transition-colors text-left flex-shrink-0"
		>
			{/* ... existing chevron, icon, "Changes" text, badge ... */}
		</button>
	</ContextMenuTrigger>
	<ContextMenuContent>
		<ContextMenuItem
			disabled={!hasChanges || disabled}
			onClick={() => setShowDiscardAllConfirm(true)}
		>
			<Undo2 className="h-4 w-4 mr-2" />
			Discard All Changes
		</ContextMenuItem>
	</ContextMenuContent>
</ContextMenu>
```

Add the AlertDialog at the end of the ChangesSection return, before the closing `</div>`:

```tsx
<AlertDialog open={showDiscardAllConfirm} onOpenChange={setShowDiscardAllConfirm}>
	<AlertDialogContent>
		<AlertDialogHeader>
			<AlertDialogTitle>Discard All Changes?</AlertDialogTitle>
			<AlertDialogDescription>
				This will discard all {changedFiles.length} uncommitted change(s). This cannot be undone.
			</AlertDialogDescription>
		</AlertDialogHeader>
		<AlertDialogFooter>
			<AlertDialogCancel>Cancel</AlertDialogCancel>
			<AlertDialogAction
				onClick={onDiscardAll}
				className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
			>
				Discard All
			</AlertDialogAction>
		</AlertDialogFooter>
	</AlertDialogContent>
</AlertDialog>
```

**Step 3: Test manually**

Start dev stack, make some file changes, right-click the "Changes" header, verify context menu appears, click "Discard All Changes", verify confirmation dialog, confirm, verify all changes discarded.

**Step 4: Commit**

```bash
git add client/src/components/editor/SourceControlPanel.tsx
git commit -m "feat: add discard all changes context menu to source control"
```

---

### Task 2: Batch Mapping Save — Backend Endpoint

**Files:**
- Modify: `api/src/models/contracts/integrations.py` (new request/response models)
- Modify: `api/src/models/__init__.py` (re-export new models)
- Modify: `api/src/routers/integrations.py` (new batch handler)

**Step 1: Add Pydantic models**

In `api/src/models/contracts/integrations.py`, after the `IntegrationMappingUpdate` class (around line 195), add:

```python
class IntegrationMappingBatchItem(BaseModel):
    """A single mapping in a batch upsert request."""

    organization_id: UUID = Field(
        ...,
        description="Organization ID to map",
    )
    entity_id: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="External entity ID",
    )
    entity_name: str | None = Field(
        default=None,
        max_length=255,
        description="Display name for the external entity",
    )


class IntegrationMappingBatchRequest(BaseModel):
    """Batch upsert request for integration mappings."""

    mappings: list[IntegrationMappingBatchItem] = Field(
        ...,
        min_length=1,
        max_length=500,
        description="List of mappings to create or update",
    )


class IntegrationMappingBatchResponse(BaseModel):
    """Response from batch mapping upsert."""

    created: int = Field(..., description="Number of new mappings created")
    updated: int = Field(..., description="Number of existing mappings updated")
    errors: list[str] = Field(default_factory=list, description="Error messages for failed items")
```

**Step 2: Export new models**

In `api/src/models/__init__.py`, add the three new models to the import from contracts and to `__all__`.

In the `from .contracts.integrations import` block, add:
```python
IntegrationMappingBatchItem,
IntegrationMappingBatchRequest,
IntegrationMappingBatchResponse,
```

In `__all__`, add the same three names.

**Step 3: Add batch endpoint handler**

In `api/src/routers/integrations.py`, after the `update_mapping` handler (around line 1171), add:

```python
@router.post(
    "/{integration_id}/mappings/batch",
    response_model=IntegrationMappingBatchResponse,
    summary="Batch upsert integration mappings",
    description="Create or update multiple mappings in a single request (Platform admin only)",
)
async def batch_upsert_mappings(
    integration_id: UUID,
    request: IntegrationMappingBatchRequest,
    ctx: Context,
    user: CurrentSuperuser,
) -> IntegrationMappingBatchResponse:
    """Batch create/update integration mappings."""
    repo = IntegrationsRepository(ctx.db)

    # Verify integration exists
    integration = await repo.get_integration_by_id(integration_id)
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found",
        )

    created = 0
    updated = 0
    errors: list[str] = []

    for item in request.mappings:
        try:
            existing = await repo.get_mapping_by_org(integration_id, item.organization_id)
            if existing:
                # Update existing mapping
                update_data = IntegrationMappingUpdate(
                    entity_id=item.entity_id,
                    entity_name=item.entity_name,
                )
                await repo.update_mapping(existing.id, update_data, updated_by=user.email)
                updated += 1
            else:
                # Create new mapping
                create_data = IntegrationMappingCreate(
                    organization_id=item.organization_id,
                    entity_id=item.entity_id,
                    entity_name=item.entity_name,
                )
                await repo.create_mapping(integration_id, create_data, updated_by=user.email)
                created += 1
        except Exception as e:
            errors.append(f"org {item.organization_id}: {str(e)}")
            logger.error(f"Batch mapping error for org {item.organization_id}: {e}")

    await ctx.db.commit()

    logger.info(
        f"Batch upsert for integration {integration_id}: "
        f"created={created}, updated={updated}, errors={len(errors)}"
    )

    return IntegrationMappingBatchResponse(
        created=created,
        updated=updated,
        errors=errors,
    )
```

Add the new models to the import at the top of the file:
```python
from src.models import (
    ...
    IntegrationMappingBatchRequest,
    IntegrationMappingBatchResponse,
    IntegrationMappingUpdate,
    IntegrationMappingCreate,
    ...
)
```

Note: `IntegrationMappingCreate` and `IntegrationMappingUpdate` should already be imported. Just add the batch models.

**Step 4: Run pyright and ruff**

```bash
cd api && pyright && ruff check .
```

**Step 5: Commit**

```bash
git add api/src/models/contracts/integrations.py api/src/models/__init__.py api/src/routers/integrations.py
git commit -m "feat: add batch upsert endpoint for integration mappings"
```

---

### Task 3: Batch Mapping Save — Frontend Integration

**Files:**
- Modify: `client/src/pages/IntegrationDetail.tsx` (rewrite handleSaveAll)
- Modify: `client/src/services/integrations.ts` (optional: batch mutation hook)

**Step 1: Regenerate TypeScript types**

```bash
cd client && npm run generate:types
```

This picks up the new batch endpoint from the OpenAPI spec.

**Step 2: Add batch mutation hook**

In `client/src/services/integrations.ts`, after `useDeleteMapping`, add:

```typescript
/**
 * Hook to batch upsert integration mappings
 */
export function useBatchUpsertMappings() {
	const queryClient = useQueryClient();

	return $api.useMutation(
		"post",
		"/api/integrations/{integration_id}/mappings/batch",
		{
			onSuccess: (_, variables) => {
				const integrationId = variables.params.path.integration_id;
				queryClient.invalidateQueries({
					queryKey: [
						"get",
						"/api/integrations/{integration_id}",
						{ params: { path: { integration_id: integrationId } } },
					],
				});
			},
		},
	);
}
```

**Step 3: Rewrite handleSaveAll in IntegrationDetail**

Import `useBatchUpsertMappings` from services. Add the hook:

```typescript
const batchMutation = useBatchUpsertMappings();
```

Replace `handleSaveAll` (lines 435-469) with:

```typescript
const handleSaveAll = async () => {
	const dirtyMappings = orgsWithMappings.filter(
		(org) => org.isDirty && org.formData.entity_id,
	);

	if (dirtyMappings.length === 0) {
		toast.info("No changes to save");
		return;
	}

	setIsSavingAll(true);
	try {
		const result = await batchMutation.mutateAsync({
			params: { path: { integration_id: integrationId! } },
			body: {
				mappings: dirtyMappings.map((org) => ({
					organization_id: org.id,
					entity_id: org.formData.entity_id,
					entity_name: org.formData.entity_name || undefined,
				})),
			},
		});

		// Clear dirty state for all saved mappings
		setDirtyEdits((prev) => {
			const next = new Map(prev);
			for (const org of dirtyMappings) {
				next.delete(org.id);
			}
			return next;
		});

		const total = result.created + result.updated;
		if (result.errors.length === 0) {
			toast.success(`Saved ${total} mapping(s)`);
		} else {
			toast.warning(
				`Saved ${total} mapping(s), ${result.errors.length} failed`,
			);
		}
	} catch {
		toast.error("Failed to save mappings");
	} finally {
		setIsSavingAll(false);
	}
};
```

**Step 4: Run frontend type checks**

```bash
cd client && npm run tsc && npm run lint
```

**Step 5: Commit**

```bash
git add client/src/services/integrations.ts client/src/pages/IntegrationDetail.tsx client/src/lib/v1.d.ts
git commit -m "feat: use batch endpoint for save-all integration mappings"
```

---

### Task 4: Test batch endpoint

**Files:**
- Create: `api/tests/unit/test_batch_mappings.py`

**Step 1: Write unit test for batch endpoint**

```python
"""Tests for batch mapping upsert endpoint."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestBatchUpsertMappings:
    """Tests for POST /api/integrations/{id}/mappings/batch."""

    async def test_batch_create_new_mappings(
        self, client: AsyncClient, test_integration, test_organizations
    ):
        """Batch creating mappings for unmapped orgs."""
        response = await client.post(
            f"/api/integrations/{test_integration.id}/mappings/batch",
            json={
                "mappings": [
                    {
                        "organization_id": str(test_organizations[0].id),
                        "entity_id": "ext-1",
                        "entity_name": "External 1",
                    },
                    {
                        "organization_id": str(test_organizations[1].id),
                        "entity_id": "ext-2",
                        "entity_name": "External 2",
                    },
                ]
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["created"] == 2
        assert data["updated"] == 0
        assert data["errors"] == []

    async def test_batch_update_existing_mappings(
        self, client: AsyncClient, test_integration, test_mapping
    ):
        """Batch updating an already-mapped org."""
        response = await client.post(
            f"/api/integrations/{test_integration.id}/mappings/batch",
            json={
                "mappings": [
                    {
                        "organization_id": str(test_mapping.organization_id),
                        "entity_id": "new-entity-id",
                        "entity_name": "New Name",
                    },
                ]
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["created"] == 0
        assert data["updated"] == 1

    async def test_batch_mixed_create_and_update(
        self, client: AsyncClient, test_integration, test_mapping, test_organizations
    ):
        """Batch with a mix of new and existing mappings."""
        unmapped_org = [o for o in test_organizations if o.id != test_mapping.organization_id][0]
        response = await client.post(
            f"/api/integrations/{test_integration.id}/mappings/batch",
            json={
                "mappings": [
                    {
                        "organization_id": str(test_mapping.organization_id),
                        "entity_id": "updated-id",
                    },
                    {
                        "organization_id": str(unmapped_org.id),
                        "entity_id": "new-id",
                        "entity_name": "New Org",
                    },
                ]
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["created"] == 1
        assert data["updated"] == 1

    async def test_batch_empty_list_rejected(
        self, client: AsyncClient, test_integration
    ):
        """Empty mappings list should be rejected by validation."""
        response = await client.post(
            f"/api/integrations/{test_integration.id}/mappings/batch",
            json={"mappings": []},
        )
        assert response.status_code == 422

    async def test_batch_nonexistent_integration(
        self, client: AsyncClient
    ):
        """Batch against non-existent integration returns 404."""
        response = await client.post(
            "/api/integrations/00000000-0000-0000-0000-000000000000/mappings/batch",
            json={
                "mappings": [
                    {
                        "organization_id": "00000000-0000-0000-0000-000000000001",
                        "entity_id": "ext-1",
                    }
                ]
            },
        )
        assert response.status_code == 404
```

Note: The exact test fixtures (`test_integration`, `test_organizations`, `test_mapping`) will depend on what's already available in the test conftest. Check `api/tests/conftest.py` and `api/tests/e2e/conftest.py` for existing fixtures and adapt accordingly. These tests may need to be E2E tests if they require a real database.

**Step 2: Run tests**

```bash
./test.sh tests/unit/test_batch_mappings.py -v
```

Adapt fixture names and test structure based on what exists.

**Step 3: Commit**

```bash
git add api/tests/
git commit -m "test: add tests for batch mapping upsert endpoint"
```

---

### Task 5: Final Verification

**Step 1: Run full backend checks**

```bash
cd api && pyright && ruff check .
```

**Step 2: Run full frontend checks**

```bash
cd client && npm run tsc && npm run lint
```

**Step 3: Run full test suite**

```bash
./test.sh
```

**Step 4: Manual smoke test**

1. Source control: Make changes → right-click Changes header → Discard All → confirm → changes gone
2. Integrations: Auto-match entities → Accept All → Save All → single request in network tab → single toast
