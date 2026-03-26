// CSP Tenant table with linking, GDAP status, consent actions, and batch selection

interface CspTenant {
  tenant_id: string;
  tenant_name: string;
  domain: string;
  customer_id: string;
  bifrost_org_id: string | null;
  bifrost_org_name: string | null;
  consent_status: "none" | "granted" | "partial" | "failed";
  consent_error?: string;
  consent_execution_id?: string;
  gdap_status?: "active" | "approvalPending" | "created" | "terminated" | "none";
  gdap_relationship_id?: string;
  gdap_approval_url?: string | null;
}

interface Organization {
  label: string;
  value: string;
}

interface BatchConsentProgress {
  total: number;
  current: number;
  currentTenantName: string;
}

interface TenantTableProps {
  tenants: CspTenant[];
  organizations: Organization[];
  loading: boolean;
  onLinkChange: (tenant: CspTenant, orgId: string) => void;
  onCreateOrg: (tenant: CspTenant) => void;
  onConsent: (tenant: CspTenant) => void;
  onBatchConsent: (tenants: CspTenant[]) => void;
  onRefresh: (tenant: CspTenant) => void;
  onCreateGdap: (tenant: CspTenant) => void;
  onSyncGdap: (tenant: CspTenant) => void;
  onCopyGdapLink: (tenant: CspTenant) => void;
  onBatchSyncGdap: () => void;
  actionLoading: Record<string, string>;
  actionSuccess: Record<string, boolean>;
  consentDisabled: boolean;
  batchProgress: BatchConsentProgress | null;
}

const CREATE_ORG_VALUE = "__create_new__";

// Configure your indirect reseller relationship link from Microsoft Partner Center
// Format: https://admin.microsoft.com/Adminportal/Home?invType=IndirectResellerRelationship&partnerId=YOUR_PARTNER_ID&msppId=YOUR_MSPP_ID&indirectCSPId=YOUR_CSP_ID#/BillingAccounts/partner-invitation
const RESELLER_LINK = "";

export function TenantTable({
  tenants,
  organizations,
  loading,
  onLinkChange,
  onCreateOrg,
  onConsent,
  onBatchConsent,
  onRefresh,
  onCreateGdap,
  onSyncGdap,
  onCopyGdapLink,
  onBatchSyncGdap,
  actionLoading,
  actionSuccess,
  consentDisabled,
  batchProgress,
}: TenantTableProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "granted" | "partial" | "none" | "failed">("all");
  const [selectedTenantIds, setSelectedTenantIds] = useState<Set<string>>(new Set());
  const [resellerLinkCopied, setResellerLinkCopied] = useState(false);

  const isLinking = (tenantId: string) => !!actionLoading[`link-${tenantId}`];
  const isConsenting = (tenantId: string) => !!actionLoading[`consent-${tenantId}`];
  const isRefreshing = (tenantId: string) => !!actionLoading[`refresh-${tenantId}`];
  const refreshSucceeded = (tenantId: string) => !!actionSuccess[`refresh-${tenantId}`];
  const isGdapCreating = (tenantId: string) => !!actionLoading[`gdap-create-${tenantId}`];
  const isGdapSyncing = (tenantId: string) => !!actionLoading[`gdap-sync-${tenantId}`];
  const gdapCopySucceeded = (tenantId: string) => !!actionSuccess[`gdap-copy-${tenantId}`];
  const gdapCreateSucceeded = (tenantId: string) => !!actionSuccess[`gdap-create-${tenantId}`];
  const gdapSyncSucceeded = (tenantId: string) => !!actionSuccess[`gdap-sync-${tenantId}`];
  const isBatchSyncingGdap = !!actionLoading["gdap-batch-sync"];
  const batchSyncGdapSucceeded = !!actionSuccess["gdap-batch-sync"];

  const activeGdapCount = useMemo(() => {
    return tenants.filter((t) => t.gdap_status === "active").length;
  }, [tenants]);

  const filteredTenants = useMemo(() => {
    return tenants.filter((tenant) => {
      if (statusFilter !== "all" && tenant.consent_status !== statusFilter) {
        return false;
      }

      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const matchesName = tenant.tenant_name.toLowerCase().includes(query);
        const matchesDomain = tenant.domain.toLowerCase().includes(query);
        const matchesTenantId = tenant.tenant_id.toLowerCase().includes(query);
        const matchesOrgName = tenant.bifrost_org_name?.toLowerCase().includes(query) || false;

        if (!matchesName && !matchesDomain && !matchesTenantId && !matchesOrgName) {
          return false;
        }
      }

      return true;
    });
  }, [tenants, searchQuery, statusFilter]);

  const consentableTenants = useMemo(() => {
    return filteredTenants.filter((t) => !!t.bifrost_org_id);
  }, [filteredTenants]);

  const selectedConsentable = useMemo(() => {
    return consentableTenants.filter((t) => selectedTenantIds.has(t.tenant_id));
  }, [consentableTenants, selectedTenantIds]);

  const allConsentableSelected = consentableTenants.length > 0 &&
    consentableTenants.every((t) => selectedTenantIds.has(t.tenant_id));

  const someConsentableSelected = selectedConsentable.length > 0 && !allConsentableSelected;

  const toggleTenant = (tenantId: string) => {
    setSelectedTenantIds((prev) => {
      const next = new Set(prev);
      if (next.has(tenantId)) {
        next.delete(tenantId);
      } else {
        next.add(tenantId);
      }
      return next;
    });
  };

  const toggleAllConsentable = () => {
    if (allConsentableSelected) {
      setSelectedTenantIds(new Set());
    } else {
      setSelectedTenantIds(new Set(consentableTenants.map((t) => t.tenant_id)));
    }
  };

  const handleBatchConsent = () => {
    if (selectedConsentable.length === 0) return;
    onBatchConsent(selectedConsentable);
    setSelectedTenantIds(new Set());
  };

  const isSelectable = (tenant: CspTenant) => {
    return !!tenant.bifrost_org_id;
  };

  const mappedOrgIds = useMemo(() => {
    return new Set(
      tenants
        .map((t) => t.bifrost_org_id)
        .filter(Boolean)
        .map((id) => String(id))
    );
  }, [tenants]);

  const getAvailableOrgs = (tenant: CspTenant) => {
    return organizations.filter((org) => {
      const orgId = String(org.value);
      const tenantOrgId = tenant.bifrost_org_id ? String(tenant.bifrost_org_id) : null;
      if (orgId === tenantOrgId) return true;
      return !mappedOrgIds.has(orgId);
    });
  };

  const handleCopyResellerLink = () => {
    navigator.clipboard.writeText(RESELLER_LINK);
    setResellerLinkCopied(true);
    setTimeout(() => setResellerLinkCopied(false), 2000);
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <Skeleton className="h-10 w-64" />
          <Skeleton className="h-10 w-40" />
        </div>
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      </div>
    );
  }

  // -- GDAP column: badge + inline action --
  const renderGdapCell = (tenant: CspTenant) => {
    const status = tenant.gdap_status;

    if (status === "active") {
      return (
        <Badge variant="default" className="bg-green-600 hover:bg-green-700">
          <CheckCircle2 className="w-3 h-3 mr-1" />
          Active
        </Badge>
      );
    }

    if (status === "approvalPending" || status === "created") {
      return (
        <div className="flex items-center gap-1.5">
          <Badge variant="default" className="bg-yellow-600 hover:bg-yellow-700">
            <Clock className="w-3 h-3 mr-1" />
            Pending
          </Badge>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  className={`h-7 w-7 p-0 ${gdapCopySucceeded(tenant.tenant_id) ? "text-green-500" : ""}`}
                  onClick={() => onCopyGdapLink(tenant)}
                >
                  {gdapCopySucceeded(tenant.tenant_id) ? (
                    <Check className="w-3.5 h-3.5" />
                  ) : (
                    <Copy className="w-3.5 h-3.5" />
                  )}
                </Button>
              </TooltipTrigger>
              <TooltipContent>Copy approval link</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      );
    }

    if (status === "terminated") {
      return (
        <div className="flex items-center gap-1.5">
          <Badge variant="destructive">
            <XCircle className="w-3 h-3 mr-1" />
            Terminated
          </Badge>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2"
            onClick={() => onCreateGdap(tenant)}
            disabled={isGdapCreating(tenant.tenant_id) || !tenant.bifrost_org_id || !!batchProgress}
          >
            {isGdapCreating(tenant.tenant_id) ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : gdapCreateSucceeded(tenant.tenant_id) ? (
              <Check className="w-3.5 h-3.5 text-green-500" />
            ) : (
              <Plus className="w-3.5 h-3.5" />
            )}
          </Button>
        </div>
      );
    }

    // none / no relationship
    return (
      <Button
        variant="outline"
        size="sm"
        onClick={() => onCreateGdap(tenant)}
        disabled={isGdapCreating(tenant.tenant_id) || !tenant.bifrost_org_id || !!batchProgress}
      >
        {isGdapCreating(tenant.tenant_id) ? (
          <Loader2 className="w-4 h-4 mr-1 animate-spin" />
        ) : gdapCreateSucceeded(tenant.tenant_id) ? (
          <Check className="w-4 h-4 mr-1 text-green-500" />
        ) : (
          <Plus className="w-4 h-4 mr-1" />
        )}
        Create
      </Button>
    );
  };

  // -- Roles column: sync button when GDAP active --
  const renderRolesCell = (tenant: CspTenant) => {
    if (tenant.gdap_status !== "active") {
      return (
        <span className="text-muted-foreground">—</span>
      );
    }

    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              onClick={() => onSyncGdap(tenant)}
              disabled={isGdapSyncing(tenant.tenant_id) || !!batchProgress}
              className={gdapSyncSucceeded(tenant.tenant_id) ? "text-green-500 border-green-500" : ""}
            >
              {isGdapSyncing(tenant.tenant_id) ? (
                <Loader2 className="w-4 h-4 mr-1 animate-spin" />
              ) : gdapSyncSucceeded(tenant.tenant_id) ? (
                <Check className="w-4 h-4 mr-1" />
              ) : (
                <RefreshCw className="w-4 h-4 mr-1" />
              )}
              Sync
            </Button>
          </TooltipTrigger>
          <TooltipContent>Sync security group role assignments from template</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  };

  // -- Consent column: morphing button --
  const renderConsentCell = (tenant: CspTenant) => {
    const executionLink = tenant.consent_execution_id
      ? `/history/${tenant.consent_execution_id}`
      : null;

    const gdapActive = tenant.gdap_status === "active";
    const hasOrg = !!tenant.bifrost_org_id;
    const prerequisitesMet = gdapActive && hasOrg && !consentDisabled;
    const status = tenant.consent_status;

    // Determine button props based on status
    let variant: "default" | "outline" | "destructive" = "default";
    let colorClass = "";
    let icon = <Play className="w-4 h-4 mr-1" />;
    let label = "Consent";
    let onClick: (() => void) | undefined = () => onConsent(tenant);
    let disabled = !!batchProgress;
    let tooltipContent: React.ReactNode = null;

    if (status === "granted") {
      colorClass = "bg-green-600 hover:bg-green-700";
      icon = <Check className="w-4 h-4 mr-1" />;
      label = "Consented";
      onClick = () => onRefresh(tenant);
      disabled = disabled || isRefreshing(tenant.tenant_id);
      tooltipContent = "Click to refresh consent status";

      // Override icon for loading/success states
      if (isRefreshing(tenant.tenant_id)) {
        icon = <Loader2 className="w-4 h-4 mr-1 animate-spin" />;
      } else if (refreshSucceeded(tenant.tenant_id)) {
        colorClass = "bg-green-600 hover:bg-green-700";
      }
    } else if (status === "partial") {
      colorClass = "bg-yellow-600 hover:bg-yellow-700";
      icon = <AlertTriangle className="w-4 h-4 mr-1" />;
      label = "Partial";
      disabled = disabled || isConsenting(tenant.tenant_id) || !prerequisitesMet;
      tooltipContent = (
        <>
          <p>{tenant.consent_error || "Some permissions failed to apply."}</p>
          {executionLink && (
            <p className="text-xs mt-1 opacity-75">
              <a href={executionLink} target="_blank" rel="noopener noreferrer" className="underline">
                View execution details
              </a>
            </p>
          )}
        </>
      );

      if (isConsenting(tenant.tenant_id)) {
        icon = <Loader2 className="w-4 h-4 mr-1 animate-spin" />;
      }
    } else if (status === "failed") {
      variant = "destructive";
      icon = <AlertTriangle className="w-4 h-4 mr-1" />;
      label = "Failed";
      disabled = disabled || isConsenting(tenant.tenant_id) || !prerequisitesMet;
      tooltipContent = (
        <>
          <p>{tenant.consent_error || "Consent failed. Click to retry."}</p>
          {executionLink && (
            <p className="text-xs mt-1 opacity-75">
              <a href={executionLink} target="_blank" rel="noopener noreferrer" className="underline">
                View execution details
              </a>
            </p>
          )}
        </>
      );

      if (isConsenting(tenant.tenant_id)) {
        icon = <Loader2 className="w-4 h-4 mr-1 animate-spin" />;
      }
    } else if (status === "none" && !prerequisitesMet) {
      // Not ready — outline disabled
      variant = "outline";
      icon = <span className="mr-1">—</span>;
      label = "Consent";
      disabled = true;
      onClick = undefined;
      tooltipContent = !hasOrg
        ? "Link a Bifrost organization first"
        : !gdapActive
          ? "GDAP must be active before consent"
          : "Complete setup and configure permissions first";
    } else {
      // none + ready — primary filled
      disabled = disabled || isConsenting(tenant.tenant_id);

      if (isConsenting(tenant.tenant_id)) {
        icon = <Loader2 className="w-4 h-4 mr-1 animate-spin" />;
      }
    }

    const button = (
      <Button
        variant={variant}
        size="sm"
        onClick={onClick}
        disabled={disabled}
        className={colorClass}
      >
        {icon}
        {label}
      </Button>
    );

    if (tooltipContent) {
      return (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <span>{button}</span>
            </TooltipTrigger>
            <TooltipContent className="max-w-sm">{tooltipContent}</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      );
    }

    return button;
  };

  if (tenants.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <Building2 className="w-12 h-12 text-muted-foreground mb-4" />
        <h3 className="text-lg font-medium mb-1">No CSP tenants found</h3>
        <p className="text-muted-foreground text-sm">
          CSP customer tenants will appear here once they are synced from Partner Center.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Filters and Batch Actions */}
      <div className="flex items-center gap-3 mb-4">
        <div className="relative w-64 shrink-0">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search tenants..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{ paddingLeft: "2.5rem" }}
          />
        </div>
        <Select
          value={statusFilter}
          onValueChange={(value) => setStatusFilter(value as typeof statusFilter)}
        >
          <SelectTrigger className="w-40 shrink-0">
            <SelectValue placeholder="Filter status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="granted">Consented</SelectItem>
            <SelectItem value="partial">Partial</SelectItem>
            <SelectItem value="none">Not consented</SelectItem>
            <SelectItem value="failed">Failed</SelectItem>
          </SelectContent>
        </Select>
        <div className="text-sm text-muted-foreground shrink-0">
          {filteredTenants.length === tenants.length
            ? `${tenants.length} tenants`
            : `${filteredTenants.length} of ${tenants.length} tenants`}
        </div>

        {/* Batch actions */}
        <div className="ml-auto flex items-center gap-2 shrink-0">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleCopyResellerLink}
                  className={resellerLinkCopied ? "text-green-500 border-green-500" : ""}
                >
                  {resellerLinkCopied ? (
                    <Check className="w-4 h-4 mr-1" />
                  ) : (
                    <Copy className="w-4 h-4 mr-1" />
                  )}
                  Reseller Link
                </Button>
              </TooltipTrigger>
              <TooltipContent>Copy Pax8 indirect reseller invitation link</TooltipContent>
            </Tooltip>
          </TooltipProvider>

          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={onBatchSyncGdap}
                  disabled={isBatchSyncingGdap || activeGdapCount === 0 || !!batchProgress}
                >
                  {isBatchSyncingGdap ? (
                    <Loader2 className="w-4 h-4 mr-1 animate-spin" />
                  ) : batchSyncGdapSucceeded ? (
                    <Check className="w-4 h-4 mr-1 text-green-500" />
                  ) : (
                    <RefreshCw className="w-4 h-4 mr-1" />
                  )}
                  Sync Roles ({activeGdapCount})
                </Button>
              </TooltipTrigger>
              <TooltipContent>Sync role assignments from template for all active GDAP relationships</TooltipContent>
            </Tooltip>
          </TooltipProvider>

          {!consentDisabled && consentableTenants.length > 0 && (
            <>
              {batchProgress ? (
                <div className="flex items-center gap-3 min-w-0">
                  <div className="flex items-center gap-2 text-sm text-muted-foreground shrink-0">
                    <Loader2 className="w-4 h-4 animate-spin text-primary" />
                    <span>{batchProgress.current}/{batchProgress.total}</span>
                  </div>
                  <div className="w-24 h-2 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-primary transition-all duration-300 ease-out rounded-full"
                      style={{ width: `${(batchProgress.current / batchProgress.total) * 100}%` }}
                    />
                  </div>
                  <span className="text-xs text-muted-foreground truncate max-w-[100px] shrink-0">
                    {batchProgress.currentTenantName}
                  </span>
                </div>
              ) : (
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="default"
                        size="sm"
                        onClick={handleBatchConsent}
                        disabled={selectedConsentable.length === 0}
                      >
                        <Play className="w-4 h-4 mr-1" />
                        Consent ({selectedConsentable.length})
                      </Button>
                    </TooltipTrigger>
                    {selectedConsentable.length === 0 && (
                      <TooltipContent>
                        <p>Select tenants to consent (linked, not yet consented)</p>
                      </TooltipContent>
                    )}
                  </Tooltip>
                </TooltipProvider>
              )}
            </>
          )}
        </div>
      </div>

      {/* Table */}
      {filteredTenants.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <Search className="w-12 h-12 text-muted-foreground mb-4" />
          <h3 className="text-lg font-medium mb-1">No matching tenants</h3>
          <p className="text-muted-foreground text-sm">
            Try adjusting your search or filter criteria.
          </p>
          <Button
            variant="outline"
            size="sm"
            className="mt-4"
            onClick={() => {
              setSearchQuery("");
              setStatusFilter("all");
            }}
          >
            Clear filters
          </Button>
        </div>
      ) : (
        <div className="flex-1 min-h-0 overflow-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[50px]">
                  <Checkbox
                    checked={allConsentableSelected}
                    {...(someConsentableSelected ? { "data-state": "indeterminate" } : {})}
                    onCheckedChange={toggleAllConsentable}
                    disabled={consentableTenants.length === 0 || consentDisabled || !!batchProgress}
                    aria-label="Select all"
                  />
                </TableHead>
                <TableHead className="w-[200px]">CSP Customer</TableHead>
                <TableHead className="w-[250px]">Bifrost Organization</TableHead>
                <TableHead className="w-[150px]">GDAP</TableHead>
                <TableHead className="w-[120px]">Roles</TableHead>
                <TableHead className="w-[180px]">Consent</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredTenants.map((tenant) => (
                <TableRow key={tenant.tenant_id}>
                  <TableCell>
                    <Checkbox
                      checked={selectedTenantIds.has(tenant.tenant_id)}
                      onCheckedChange={() => toggleTenant(tenant.tenant_id)}
                      disabled={!isSelectable(tenant) || consentDisabled || !!batchProgress}
                      aria-label={`Select ${tenant.tenant_name}`}
                    />
                  </TableCell>
                  <TableCell>
                    <div className="font-medium">{tenant.tenant_name}</div>
                    <div className="text-sm text-muted-foreground">{tenant.domain}</div>
                  </TableCell>
                  <TableCell>
                    <Combobox
                      options={[
                        ...(tenant.bifrost_org_id ? [{ value: "unlink", label: "Unlink organization" }] : []),
                        { value: CREATE_ORG_VALUE, label: "+ Create new organization..." },
                        ...getAvailableOrgs(tenant),
                      ]}
                      value={tenant.bifrost_org_id || ""}
                      onValueChange={(value) => {
                        if (value === CREATE_ORG_VALUE) {
                          onCreateOrg(tenant);
                        } else {
                          onLinkChange(tenant, value);
                        }
                      }}
                      placeholder="Select org..."
                      searchPlaceholder="Search organizations..."
                      emptyText="No organization found."
                      disabled={isLinking(tenant.tenant_id) || !!batchProgress}
                      isLoading={isLinking(tenant.tenant_id)}
                    />
                  </TableCell>
                  <TableCell>{renderGdapCell(tenant)}</TableCell>
                  <TableCell>{renderRolesCell(tenant)}</TableCell>
                  <TableCell>{renderConsentCell(tenant)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
