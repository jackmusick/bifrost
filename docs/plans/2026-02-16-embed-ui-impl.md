# Embed UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an "Embed" settings dialog to the app editor with secret CRUD and integration guide, plus change the embed entry point to redirect to the app.

**Architecture:** New `EmbedSettingsDialog` component opened from the app editor header. Uses `authFetch` for CRUD against `/api/applications/{appId}/embed-secrets`. Backend embed entry point changes from JSON to redirect. The embed secrets endpoints are not yet in the OpenAPI spec's generated types, so we use `authFetch` directly.

**Tech Stack:** React, TypeScript, shadcn/ui (Dialog, AlertDialog, Badge, Alert), lucide-react icons, authFetch, Sonner toast

**Design doc:** `docs/plans/2026-02-16-embed-ui-design.md`

---

### Task 1: Backend — Change Embed Entry Point to Redirect

**Files:**
- Modify: `api/src/routers/embed.py`
- Modify: `api/tests/e2e/api/test_embed.py`

**Step 1: Update the embed endpoint to redirect**

In `api/src/routers/embed.py`, change the return value from JSON to a `RedirectResponse`. Import `RedirectResponse` from starlette and redirect to `/apps/{slug}`:

```python
from starlette.responses import RedirectResponse
```

Replace the return block (the `response.set_cookie(...)` and `return {...}` at the end of `embed_app`) with:

```python
    # Build redirect response
    redirect = RedirectResponse(
        url=f"/apps/{app.slug}",
        status_code=302,
    )

    # Set cookie on the redirect response
    redirect.set_cookie(
        key="embed_token",
        value=embed_token,
        httponly=True,
        samesite="none",
        secure=True,
        max_age=8 * 3600,
        path="/",
    )

    # Set permissive framing headers for embed route
    redirect.headers["Content-Security-Policy"] = "frame-ancestors *"
    redirect.headers["X-Frame-Options"] = "ALLOWALL"

    return redirect
```

Remove the `response: Response` parameter from the function signature since we're returning a `RedirectResponse` directly instead of modifying the injected response.

**Step 2: Update the E2E test**

In `api/tests/e2e/api/test_embed.py`, update `test_valid_hmac_returns_embed_token`:

```python
    def test_valid_hmac_returns_embed_token(self, e2e_client, test_app_with_secret):
        app = test_app_with_secret["app"]
        secret = test_app_with_secret["secret"]
        params = {"agent_id": "42"}
        hmac_val = _compute_hmac(params, secret)

        r = e2e_client.get(
            f"/embed/apps/{app['slug']}",
            params={**params, "hmac": hmac_val},
            follow_redirects=False,
        )
        # Should redirect to /apps/{slug}
        assert r.status_code == 302, r.text
        assert f"/apps/{app['slug']}" in r.headers.get("location", "")
        # Should set an embed_token cookie
        assert "embed_token" in r.cookies
```

Also update `test_embed_workflow_execution.py` — the `embed_session` fixture needs to follow the redirect or extract the cookie from the 302:

```python
        # Get embed token via HMAC-verified entry point
        params = {"agent_id": "42"}
        hmac_val = _compute_hmac(params, raw_secret)
        r = e2e_client.get(
            f"/embed/apps/{app['slug']}",
            params={**params, "hmac": hmac_val},
            follow_redirects=False,
        )
        assert r.status_code == 302, r.text
        embed_token = r.cookies.get("embed_token")
        assert embed_token, "Expected embed_token cookie"
```

**Step 3: Run tests**

Run: `./test.sh tests/e2e/api/test_embed.py tests/e2e/api/test_embed_workflow_execution.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add api/src/routers/embed.py api/tests/e2e/api/test_embed.py api/tests/e2e/api/test_embed_workflow_execution.py
git commit -m "feat: change embed entry point from JSON to redirect"
```

---

### Task 2: Frontend — EmbedSettingsDialog Component

**Files:**
- Create: `client/src/components/app-builder/EmbedSettingsDialog.tsx`

**Step 1: Create the component**

Create `client/src/components/app-builder/EmbedSettingsDialog.tsx`. This is a Dialog component with two sections: secret management and integration guide.

```typescript
/**
 * Embed Settings Dialog
 *
 * Manages embed secrets and shows integration guide for iframe embedding.
 * Opens from the app code editor header.
 */

import { useState, useEffect, useCallback } from "react";
import {
  Plus,
  Trash2,
  Copy,
  Check,
  AlertTriangle,
  Code,
  Link,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { authFetch } from "@/lib/api-client";
import { toast } from "sonner";

// ============================================================================
// Types
// ============================================================================

interface EmbedSecret {
  id: string;
  name: string;
  is_active: boolean;
  created_at: string;
}

interface EmbedSecretCreated extends EmbedSecret {
  raw_secret: string;
}

interface Props {
  appId: string;
  appSlug: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// ============================================================================
// Component
// ============================================================================

export function EmbedSettingsDialog({
  appId,
  appSlug,
  open,
  onOpenChange,
}: Props) {
  const [secrets, setSecrets] = useState<EmbedSecret[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  // Create dialog state
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const [isCreating, setIsCreating] = useState(false);

  // Reveal dialog state (shown once after creation)
  const [revealedSecret, setRevealedSecret] = useState<EmbedSecretCreated | null>(null);
  const [copied, setCopied] = useState(false);

  // Delete confirmation state
  const [deleteTarget, setDeleteTarget] = useState<EmbedSecret | null>(null);

  // ========================================================================
  // Data fetching
  // ========================================================================

  const fetchSecrets = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await authFetch(
        `/api/applications/${appId}/embed-secrets`,
      );
      if (res.ok) {
        setSecrets(await res.json());
      }
    } catch {
      toast.error("Failed to load embed secrets");
    } finally {
      setIsLoading(false);
    }
  }, [appId]);

  useEffect(() => {
    if (open) {
      fetchSecrets();
    }
  }, [open, fetchSecrets]);

  // ========================================================================
  // Actions
  // ========================================================================

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!createName.trim()) return;

    setIsCreating(true);
    try {
      const res = await authFetch(
        `/api/applications/${appId}/embed-secrets`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: createName.trim() }),
        },
      );
      if (!res.ok) throw new Error(await res.text());
      const created: EmbedSecretCreated = await res.json();
      setRevealedSecret(created);
      setIsCreateOpen(false);
      setCreateName("");
      fetchSecrets();
      toast.success("Embed secret created");
    } catch {
      toast.error("Failed to create embed secret");
    } finally {
      setIsCreating(false);
    }
  };

  const handleToggleActive = async (secret: EmbedSecret) => {
    try {
      const res = await authFetch(
        `/api/applications/${appId}/embed-secrets/${secret.id}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ is_active: !secret.is_active }),
        },
      );
      if (!res.ok) throw new Error(await res.text());
      fetchSecrets();
      toast.success(
        secret.is_active ? "Secret deactivated" : "Secret activated",
      );
    } catch {
      toast.error("Failed to update secret");
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      const res = await authFetch(
        `/api/applications/${appId}/embed-secrets/${deleteTarget.id}`,
        { method: "DELETE" },
      );
      if (!res.ok) throw new Error(await res.text());
      setDeleteTarget(null);
      fetchSecrets();
      toast.success("Secret deleted");
    } catch {
      toast.error("Failed to delete secret");
    }
  };

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // ========================================================================
  // Code snippets
  // ========================================================================

  const embedUrl = `${window.location.origin}/embed/apps/${appSlug}`;

  const iframeSnippet = `<iframe
  src="${embedUrl}?param1=value1&hmac=COMPUTED_HMAC"
  style="width: 100%; height: 600px; border: none;"
  allow="clipboard-write"
></iframe>`;

  const pythonSnippet = `import hashlib
import hmac
from urllib.parse import urlencode

def embed_url(params: dict, secret: str) -> str:
    """Build a signed embed URL."""
    message = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    signature = hmac.new(
        secret.encode(), message.encode(), hashlib.sha256
    ).hexdigest()
    return f"${embedUrl}?{urlencode(params)}&hmac={signature}"

# Example:
url = embed_url({"agent_id": "42", "ticket_id": "1001"}, "YOUR_SECRET")`;

  const jsSnippet = `async function embedUrl(params, secret) {
  const message = Object.keys(params)
    .sort()
    .map(k => \`\${k}=\${params[k]}\`)
    .join("&");

  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, encoder.encode(message));
  const hmac = Array.from(new Uint8Array(sig))
    .map(b => b.toString(16).padStart(2, "0")).join("");

  const qs = new URLSearchParams({ ...params, hmac }).toString();
  return \`${embedUrl}?\${qs}\`;
}

// Example:
const url = await embedUrl({ agent_id: "42", ticket_id: "1001" }, "YOUR_SECRET");`;

  // ========================================================================
  // Render
  // ========================================================================

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Embed Settings</DialogTitle>
            <DialogDescription>
              Manage secrets for HMAC-authenticated iframe embedding.
            </DialogDescription>
          </DialogHeader>

          <Tabs defaultValue="secrets" className="mt-2">
            <TabsList>
              <TabsTrigger value="secrets">Secrets</TabsTrigger>
              <TabsTrigger value="guide">Integration Guide</TabsTrigger>
            </TabsList>

            {/* ============ Secrets Tab ============ */}
            <TabsContent value="secrets" className="space-y-4">
              <div className="flex items-center justify-between">
                <p className="text-sm text-muted-foreground">
                  Shared secrets used to verify embed requests via HMAC-SHA256.
                </p>
                <Button
                  size="sm"
                  onClick={() => setIsCreateOpen(true)}
                >
                  <Plus className="mr-2 h-4 w-4" />
                  Create Secret
                </Button>
              </div>

              {isLoading ? (
                <p className="text-sm text-muted-foreground py-8 text-center">
                  Loading...
                </p>
              ) : secrets.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  <Link className="h-8 w-8 mx-auto mb-2 opacity-50" />
                  <p className="text-sm">No embed secrets configured.</p>
                  <p className="text-xs mt-1">
                    Create a secret to enable iframe embedding.
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  {secrets.map((secret) => (
                    <div
                      key={secret.id}
                      className={`flex items-center justify-between p-3 rounded-lg border ${
                        secret.is_active
                          ? "border-l-4 border-l-green-500"
                          : "border-l-4 border-l-gray-300 opacity-60"
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <div>
                          <p className="text-sm font-medium">{secret.name}</p>
                          <p className="text-xs text-muted-foreground">
                            Created{" "}
                            {new Date(secret.created_at).toLocaleDateString()}
                          </p>
                        </div>
                        <Badge
                          variant={secret.is_active ? "default" : "secondary"}
                        >
                          {secret.is_active ? "Active" : "Inactive"}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleToggleActive(secret)}
                        >
                          {secret.is_active ? "Deactivate" : "Activate"}
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => setDeleteTarget(secret)}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </TabsContent>

            {/* ============ Integration Guide Tab ============ */}
            <TabsContent value="guide" className="space-y-6">
              <div>
                <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
                  <Code className="h-4 w-4" />
                  iframe HTML
                </h3>
                <div className="relative">
                  <pre className="bg-muted p-3 rounded-md text-xs overflow-x-auto">
                    {iframeSnippet}
                  </pre>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="absolute top-2 right-2 h-6 w-6"
                    onClick={() => handleCopy(iframeSnippet)}
                  >
                    <Copy className="h-3 w-3" />
                  </Button>
                </div>
              </div>

              <div>
                <h3 className="text-sm font-semibold mb-2">
                  HMAC Signing — Python
                </h3>
                <div className="relative">
                  <pre className="bg-muted p-3 rounded-md text-xs overflow-x-auto">
                    {pythonSnippet}
                  </pre>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="absolute top-2 right-2 h-6 w-6"
                    onClick={() => handleCopy(pythonSnippet)}
                  >
                    <Copy className="h-3 w-3" />
                  </Button>
                </div>
              </div>

              <div>
                <h3 className="text-sm font-semibold mb-2">
                  HMAC Signing — JavaScript
                </h3>
                <div className="relative">
                  <pre className="bg-muted p-3 rounded-md text-xs overflow-x-auto">
                    {jsSnippet}
                  </pre>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="absolute top-2 right-2 h-6 w-6"
                    onClick={() => handleCopy(jsSnippet)}
                  >
                    <Copy className="h-3 w-3" />
                  </Button>
                </div>
              </div>
            </TabsContent>
          </Tabs>
        </DialogContent>
      </Dialog>

      {/* ============ Create Secret Dialog ============ */}
      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent className="sm:max-w-md">
          <form onSubmit={handleCreate}>
            <DialogHeader>
              <DialogTitle>Create Embed Secret</DialogTitle>
              <DialogDescription>
                Create a shared secret for HMAC-authenticated embedding.
                A secret will be auto-generated.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="secret-name">Name</Label>
                <Input
                  id="secret-name"
                  placeholder="e.g., Halo Production"
                  value={createName}
                  onChange={(e) => setCreateName(e.target.value)}
                  autoFocus
                />
              </div>
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setIsCreateOpen(false)}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={isCreating || !createName.trim()}>
                {isCreating ? "Creating..." : "Create Secret"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* ============ One-Time Reveal Dialog ============ */}
      <Dialog
        open={!!revealedSecret}
        onOpenChange={(open) => {
          if (!open) setRevealedSecret(null);
        }}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Check className="h-5 w-5 text-green-500" />
              Secret Created
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>
                Copy this secret now. It will not be shown again.
              </AlertDescription>
            </Alert>
            <div className="flex gap-2">
              <Input
                value={revealedSecret?.raw_secret || ""}
                readOnly
                className="font-mono text-sm"
              />
              <Button
                variant="outline"
                size="icon"
                onClick={() =>
                  handleCopy(revealedSecret?.raw_secret || "")
                }
              >
                {copied ? (
                  <Check className="h-4 w-4" />
                ) : (
                  <Copy className="h-4 w-4" />
                )}
              </Button>
            </div>
          </div>
          <DialogFooter>
            <Button onClick={() => setRevealedSecret(null)}>Done</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ============ Delete Confirmation ============ */}
      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete embed secret?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete &quot;{deleteTarget?.name}&quot;.
              Any integrations using this secret will stop working.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete}>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
```

**Step 2: Commit**

```bash
git add client/src/components/app-builder/EmbedSettingsDialog.tsx
git commit -m "feat: add EmbedSettingsDialog component"
```

---

### Task 3: Frontend — Wire Up Dialog in App Editor

**Files:**
- Modify: `client/src/pages/AppCodeEditorPage.tsx`

**Step 1: Add import, state, and button**

Add import at the top of `AppCodeEditorPage.tsx`:

```typescript
import { EmbedSettingsDialog } from "@/components/app-builder/EmbedSettingsDialog";
```

Add the `Link` icon import alongside existing lucide imports:

```typescript
import { ArrowLeft, Upload, Settings, Loader2, Link } from "lucide-react";
```

Add state variable alongside the existing `isSettingsOpen`:

```typescript
const [isEmbedOpen, setIsEmbedOpen] = useState(false);
```

Add the embed button and dialog in the header bar, right before the Settings button (inside the `<div className="flex items-center gap-2">` block):

```tsx
{/* Embed */}
{isEditing && existingApp && (
  <>
    <Button
      variant="ghost"
      size="icon"
      onClick={() => setIsEmbedOpen(true)}
      title="Embed settings"
    >
      <Link className="h-4 w-4" />
    </Button>
    <EmbedSettingsDialog
      appId={existingApp.id}
      appSlug={existingApp.slug}
      open={isEmbedOpen}
      onOpenChange={setIsEmbedOpen}
    />
  </>
)}
```

**Step 2: Run TypeScript check**

Run: `cd client && npm run tsc`
Expected: PASS (no type errors)

**Step 3: Run lint**

Run: `cd client && npm run lint`
Expected: PASS

**Step 4: Commit**

```bash
git add client/src/pages/AppCodeEditorPage.tsx
git commit -m "feat: wire up embed settings dialog in app editor"
```

---

### Task 4: Verification — Full Test Suite and Manual Check

**Step 1: Run full backend test suite**

Run: `./test.sh`
Expected: All tests pass

**Step 2: Run frontend checks**

Run: `cd client && npm run tsc && npm run lint`
Expected: PASS

**Step 3: Commit any fixes**

```bash
git add -A
git commit -m "fix: address lint/test issues from embed UI"
```
