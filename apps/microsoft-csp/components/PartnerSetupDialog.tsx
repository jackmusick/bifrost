// Partner tenant setup dialog with PIM elevation instructions

interface PartnerSetupDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  applicationCount: number;
  onApplyPermissions: () => void;
  applyLoading: boolean;
  applyResult: {
    success?: boolean;
    granted_count?: number;
    granted?: Array<{ permission: string; api: string; status?: string }>;
    errors?: Array<{ permission?: string; api?: string; error: string }>;
  } | null;
}

export function PartnerSetupDialog({
  open,
  onOpenChange,
  applicationCount,
  onApplyPermissions,
  applyLoading,
  applyResult,
}: PartnerSetupDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Building className="w-5 h-5" />
            Apply to Partner Tenant
          </DialogTitle>
          <DialogDescription>
            Grant application permissions to your own tenant before rolling out to customers.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Instructions */}
          <div className="bg-muted/50 rounded-lg p-4 text-sm space-y-3">
            <p className="text-muted-foreground">
              Your GDAP user needs admin rights to grant app permissions in your own tenant:
            </p>
            <ol className="text-muted-foreground space-y-2 list-decimal list-inside">
              <li>
                <strong>PIM elevate</strong> to{" "}
                <span className="font-mono text-xs bg-muted px-1 py-0.5 rounded">
                  Cloud Application Administrator
                </span>
              </li>
              <li>
                <strong>Reconnect Microsoft CSP</strong> integration to refresh your token
              </li>
              <li>
                <strong>Click Apply</strong> below
              </li>
            </ol>
          </div>

          {/* Status */}
          <div className="flex items-center justify-between py-2">
            <span className="text-sm">
              {applicationCount} application permission{applicationCount !== 1 ? "s" : ""} to grant
            </span>
          </div>

          {/* Result */}
          {applyResult && (
            <div
              className={`rounded-lg p-3 text-sm ${
                applyResult.success
                  ? "bg-green-500/10 border border-green-500/20"
                  : "bg-red-500/10 border border-red-500/20"
              }`}
            >
              {applyResult.success ? (
                <div className="flex items-center gap-2 text-green-600">
                  <Check className="w-4 h-4" />
                  Granted {applyResult.granted_count} permission
                  {applyResult.granted_count !== 1 ? "s" : ""}
                </div>
              ) : (
                <div>
                  <div className="flex items-center gap-2 text-red-600">
                    <AlertTriangle className="w-4 h-4" />
                    Failed to grant permissions
                  </div>
                  {applyResult.errors?.[0]?.error && (
                    <p className="text-xs text-red-600/80 mt-1 truncate">
                      {applyResult.errors[0].error}
                    </p>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          <Button onClick={onApplyPermissions} disabled={applyLoading || applicationCount === 0}>
            {applyLoading ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Applying...
              </>
            ) : (
              <>
                <Play className="w-4 h-4 mr-2" />
                Apply Permissions
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
