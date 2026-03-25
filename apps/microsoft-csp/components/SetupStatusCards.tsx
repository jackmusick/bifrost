// Status cards showing Microsoft CSP, Microsoft, and Permissions setup state

interface IntegrationStatus {
  name: string;
  connected: boolean;
  description: string;
  error: string | null;
}

interface SetupStatus {
  csp: IntegrationStatus;
  microsoft: IntegrationStatus;
  ready_for_consent: boolean;
}

interface PermissionCounts {
  delegated_count: number;
  application_count: number;
  total_count: number;
}

interface SetupStatusCardsProps {
  setupStatus: SetupStatus | null;
  permissionCounts: PermissionCounts | null;
  loading: boolean;
  onConfigurePermissions: () => void;
  onApplyToPartner: () => void;
}

export function SetupStatusCards({
  setupStatus,
  permissionCounts,
  loading,
  onConfigurePermissions,
  onApplyToPartner,
}: SetupStatusCardsProps) {
  // Always show skeleton while loading, regardless of whether we have data
  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        {[1, 2, 3].map((i) => (
          <Card key={i}>
            <CardContent className="pt-6">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <Skeleton className="w-9 h-9 rounded-lg" />
                  <div>
                    <Skeleton className="h-5 w-28 mb-1" />
                    <Skeleton className="h-4 w-36" />
                  </div>
                </div>
                <Skeleton className="h-6 w-20" />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  const cspConnected = setupStatus?.csp?.connected ?? false;
  const microsoftConnected = setupStatus?.microsoft?.connected ?? false;
  const hasPermissions = (permissionCounts?.total_count ?? 0) > 0;
  const hasAppPermissions = (permissionCounts?.application_count ?? 0) > 0;

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
      {/* Microsoft CSP Integration */}
      <Card className={cspConnected ? "border-green-500/50" : "border-yellow-500/50"}>
        <CardContent className="pt-6">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-3">
              <div className={`p-2 rounded-lg ${cspConnected ? "bg-green-500/10" : "bg-yellow-500/10"}`}>
                <Building2 className={`w-5 h-5 ${cspConnected ? "text-green-500" : "text-yellow-500"}`} />
              </div>
              <div>
                <h3 className="font-semibold">Microsoft CSP</h3>
                <p className="text-sm text-muted-foreground">Partner Center API</p>
              </div>
            </div>
            {cspConnected ? (
              <Badge variant="default" className="bg-green-600">
                <Check className="w-3 h-3 mr-1" />
                Connected
              </Badge>
            ) : (
              <Badge variant="secondary" className="bg-yellow-500/10 text-yellow-600">
                <AlertTriangle className="w-3 h-3 mr-1" />
                Not Connected
              </Badge>
            )}
          </div>
          {!cspConnected && (
            <p className="text-xs text-muted-foreground mt-3">
              Settings → Integrations → Microsoft CSP
            </p>
          )}
        </CardContent>
      </Card>

      {/* Microsoft Integration */}
      <Card className={microsoftConnected ? "border-green-500/50" : "border-yellow-500/50"}>
        <CardContent className="pt-6">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-3">
              <div className={`p-2 rounded-lg ${microsoftConnected ? "bg-green-500/10" : "bg-yellow-500/10"}`}>
                <Shield className={`w-5 h-5 ${microsoftConnected ? "text-green-500" : "text-yellow-500"}`} />
              </div>
              <div>
                <h3 className="font-semibold">Microsoft</h3>
                <p className="text-sm text-muted-foreground">Client Credentials</p>
              </div>
            </div>
            {microsoftConnected ? (
              <Badge variant="default" className="bg-green-600">
                <Check className="w-3 h-3 mr-1" />
                Connected
              </Badge>
            ) : (
              <Badge variant="secondary" className="bg-yellow-500/10 text-yellow-600">
                <AlertTriangle className="w-3 h-3 mr-1" />
                Not Connected
              </Badge>
            )}
          </div>
          {!microsoftConnected && (
            <p className="text-xs text-muted-foreground mt-3">
              Settings → Integrations → Microsoft
            </p>
          )}
        </CardContent>
      </Card>

      {/* Permissions */}
      <Card className={hasPermissions ? "border-green-500/50" : "border-blue-500/50"}>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className={`p-2 rounded-lg ${hasPermissions ? "bg-green-500/10" : "bg-blue-500/10"}`}>
                <Key className={`w-5 h-5 ${hasPermissions ? "text-green-500" : "text-blue-500"}`} />
              </div>
              <div>
                <h3 className="font-semibold">Permissions</h3>
                {hasPermissions ? (
                  <p className="text-sm text-muted-foreground">
                    {permissionCounts?.delegated_count ?? 0} delegated, {permissionCounts?.application_count ?? 0} app
                  </p>
                ) : (
                  <p className="text-sm text-muted-foreground">Not configured</p>
                )}
              </div>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={onConfigurePermissions}
                disabled={!cspConnected || !microsoftConnected}
              >
                <Settings className="w-4 h-4 mr-1" />
                Configure
              </Button>
              {hasAppPermissions && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={onApplyToPartner}
                  disabled={!cspConnected || !microsoftConnected}
                >
                  <Building className="w-4 h-4 mr-1" />
                  Apply to Partner
                </Button>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
