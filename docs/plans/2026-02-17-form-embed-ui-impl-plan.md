# Form Embed UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add embed secret management and integration guide as a collapsible section inside `FormInfoDialog`.

**Architecture:** Extract the embed secrets logic from `EmbedSettingsDialog` into a reusable `FormEmbedSection` component, then mount it inside `FormInfoDialog` when editing an existing form.

---

### Task 1: Create `FormEmbedSection` Component

**Files:**
- Create: `client/src/components/forms/FormEmbedSection.tsx`

**Step 1: Create the component**

Create a self-contained component that manages embed secrets inline. Extract and adapt the logic from `EmbedSettingsDialog` (`client/src/components/app-builder/EmbedSettingsDialog.tsx`).

Props:
```typescript
interface FormEmbedSectionProps {
  formId: string;
}
```

The component uses `Collapsible` from `@/components/ui/collapsible` with:
- **Trigger:** A button with `ChevronRight` icon (rotates when open), `Link` icon, and "Embed Settings" text. Style: `flex items-center gap-2 text-sm font-medium hover:underline`.
- **Content:** Two sub-sections:

**Sub-section 1: Secrets**

Adapt from `EmbedSettingsDialog` lines 77-337 but inline (no wrapping Dialog):
- State: `secrets`, `isLoading`, create form state (`createName`, `createSecret`, `isCreating`), `revealedSecret`, `deleteTarget`, `copied`
- `fetchSecrets` via `authFetch` to `GET /api/forms/${formId}/embed-secrets` — called on mount via `useEffect`
- Secrets list: same layout as app version (border-l-4 cards with name, date, badge, toggle, delete)
- "Create Secret" button opens an inline form (not a sub-dialog): name input + optional secret input + Add button. On success, show the one-time reveal alert inline with copy button.
- Delete uses `AlertDialog` (same pattern as app version)

**Sub-section 2: Integration Guide**

Adapt from `EmbedSettingsDialog` lines 201-243 and 341-399:
- Build embed URL as `${window.location.origin}/embed/forms/${formId}`
- Show three copyable code snippets: iframe HTML, Python HMAC, JavaScript HMAC
- Each in a `relative` div with `<pre className="bg-muted p-3 rounded-md text-xs overflow-x-auto">` and an absolute-positioned copy button

Imports needed:
```typescript
import { useState, useEffect, useCallback } from "react";
import { Plus, Trash2, Copy, Check, AlertTriangle, Code, Link, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { authFetch } from "@/lib/api-client";
import { toast } from "sonner";
```

**Step 2: Commit**

```
feat: add FormEmbedSection component for inline embed management
```

---

### Task 2: Wire FormEmbedSection into FormInfoDialog

**Files:**
- Modify: `client/src/components/forms/FormInfoDialog.tsx`
- Modify: `client/src/pages/FormBuilder.tsx` (pass `formId` prop)

**Step 1: Add `formId` prop to FormInfoDialog**

In `FormInfoDialogProps` interface, add:
```typescript
formId?: string;
```

Update the destructuring in the component to receive it.

**Step 2: Add the embed section**

At the bottom of the dialog content (after the launch workflow parameters section, before `DialogFooter`), add:

```typescript
{isEditing && formId && (
  <FormEmbedSection formId={formId} />
)}
```

Add the import:
```typescript
import { FormEmbedSection } from "@/components/forms/FormEmbedSection";
```

**Step 3: Pass `formId` from FormBuilder**

In `FormBuilder.tsx`, find where `FormInfoDialog` is rendered. It should already have `isEditing` set. Pass the `formId`:

```typescript
<FormInfoDialog
  // ... existing props
  formId={formId}  // from useParams()
/>
```

**Step 4: Commit**

```
feat: wire FormEmbedSection into FormInfoDialog
```

---

### Task 3: Verification

**Step 1: Frontend checks**

```bash
cd client && npm run tsc
cd client && npm run lint
```

**Step 2: Fix any issues**

**Step 3: Commit if fixes needed**

```
chore: fix lint/type issues from form embed UI
```
