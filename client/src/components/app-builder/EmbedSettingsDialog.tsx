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
  Link,
} from "lucide-react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
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
  const [createSecret, setCreateSecret] = useState("");
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
          body: JSON.stringify({
            name: createName.trim(),
            ...(createSecret.trim() && { secret: createSecret.trim() }),
          }),
        },
      );
      if (!res.ok) throw new Error(await res.text());
      const created: EmbedSecretCreated = await res.json();
      setRevealedSecret(created);
      setIsCreateOpen(false);
      setCreateName("");
      setCreateSecret("");
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
            <TabsContent value="guide" className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Embed this app in an iframe using HMAC-signed URLs.
              </p>
              <div className="relative">
                <div className="overflow-x-auto rounded-md">
                  <SyntaxHighlighter
                    language="html"
                    style={oneDark}
                    customStyle={{ margin: 0, fontSize: "0.75rem" }}
                  >
                    {iframeSnippet}
                  </SyntaxHighlighter>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="absolute top-2 right-2 h-6 w-6"
                  onClick={() => handleCopy(iframeSnippet)}
                >
                  <Copy className="h-3 w-3" />
                </Button>
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
                Provide your own secret or leave blank to auto-generate.
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
              <div className="space-y-2">
                <Label htmlFor="secret-value">Secret (optional)</Label>
                <Input
                  id="secret-value"
                  placeholder="Leave blank to auto-generate"
                  value={createSecret}
                  onChange={(e) => setCreateSecret(e.target.value)}
                  className="font-mono text-sm"
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
