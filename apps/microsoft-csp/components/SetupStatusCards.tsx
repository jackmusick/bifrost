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
  const readyForConsent = setupStatus?.ready_for_consent ?? false;
  const hasPermissions = (permissionCounts?.total_count ?? 0) > 0;
  const hasAppPermissions = (permissionCounts?.application_count ?? 0) > 0;

  return (
    <div className="space-y-4 mb-6">
      <Card className={readyForConsent ? "border-green-500/50 bg-green-500/5" : "border-yellow-500/50 bg-yellow-500/5"}>
        <CardContent className="pt-6 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div>
            <h3 className="font-semibold">Consent Readiness</h3>
            <p className="text-sm text-muted-foreground">
              {readyForConsent
                ? "Partner connection and customer app identity are both ready. You can configure permissions and start tenant consent work."
                : "Finish both Microsoft connections before expecting customer consent and GDAP actions to work cleanly."}
            </p>
          </div>
          <Badge
            variant={readyForConsent ? "default" : "secondary"}
            className={readyForConsent ? "bg-green-600" : "bg-yellow-500/10 text-yellow-700"}
          >
            {readyForConsent ? (
              <>
                <Check className="w-3 h-3 mr-1" />
                Ready for Consent
              </>
            ) : (
              <>
                <AlertTriangle className="w-3 h-3 mr-1" />
                Setup Incomplete
              </>
            )}
          </Badge>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
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
                <p className="text-sm text-muted-foreground">Partner delegated access</p>
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
          <p className="text-xs text-muted-foreground mt-3">
            {cspConnected
              ? setupStatus?.csp?.description || "Partner Center, GDAP, and consent workflows are available."
              : setupStatus?.csp?.error || "Connect this first for Partner Center, GDAP, and consent workflows."}
          </p>
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
                <p className="text-sm text-muted-foreground">Customer app identity</p>
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
          <p className="text-xs text-muted-foreground mt-3">
            {microsoftConnected
              ? setupStatus?.microsoft?.description || "The Bifrost customer app identity is configured."
              : setupStatus?.microsoft?.error || "Configure the Bifrost app identity used inside customer tenants."}
          </p>
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
          <p className="text-xs text-muted-foreground mt-3">
            {!cspConnected || !microsoftConnected
              ? "Configure both Microsoft connections first. Permission selection alone is not enough to make tenant consent work."
              : hasPermissions
                ? "Delegated and application permissions are stored separately. Apply app permissions to the partner tenant before broad rollout."
                : "Choose the smallest permission set you actually need before applying anything to the partner tenant."}
          </p>
        </CardContent>
      </Card>
      </div>
    </div>
  );
}
