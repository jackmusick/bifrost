// Microsoft CSP Management - Main page
// Components are auto-resolved from components/ directory - no imports needed

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
  // GDAP fields (merged from get_gdap_status)
  gdap_status?: "active" | "approvalPending" | "created" | "terminated" | "none";
  gdap_relationship_id?: string;
  gdap_approval_url?: string | null;
  gdap_relationships?: GdapRelationship[];
}

interface Organization {
  label: string;
  value: string;
}

interface SetupStatus {
  csp: { name: string; connected: boolean; description: string; error: string | null };
  microsoft: { name: string; connected: boolean; description: string; error: string | null };
  ready_for_consent: boolean;
}

interface PermissionCounts {
  delegated_count: number;
  application_count: number;
  total_count: number;
}

interface ApiPermissions {
  api_id: string;
  api_name: string;
  display_name: string;
  delegated_permissions: Array<{ id: string; name: string; description: string; admin_consent_required?: boolean }>;
  application_permissions: Array<{ id: string; name: string; description: string }>;
}

interface SelectedPermission {
  api_id: string;
  api_name: string;
  permission_name: string;
  permission_type: "delegated" | "application";
  required?: boolean;
}

interface BatchConsentProgress {
  total: number;
  current: number;
  currentTenantName: string;
}

interface GdapRelationship {
  id: string;
  display_name: string;
  status: string;
}

interface GdapTenantStatus {
  status: string;
  relationship_id: string;
  display_name: string;
  approval_url: string | null;
  relationships: GdapRelationship[];
}

export default function MicrosoftCspPage() {
  // Query hooks (auto-execute on mount)
  const checkSetupWorkflow = useWorkflowQuery("features/microsoft_csp/workflows/check_setup.py::check_microsoft_setup");
  const getPermissionsWorkflow = useWorkflowQuery("features/microsoft_csp/workflows/get_permissions.py::get_selected_permissions");
  const tenantsWorkflow = useWorkflowQuery("features/microsoft_csp/workflows/list_tenants.py::list_csp_tenants");
  const gdapStatusWorkflow = useWorkflowQuery("features/microsoft_csp/workflows/get_gdap_status.py::get_gdap_status");

  // Mutation hooks (triggered by user action)
  const listPermissionsWorkflow = useWorkflowMutation("features/microsoft_csp/workflows/list_permissions.py::list_available_permissions");
  const savePermissionsWorkflow = useWorkflowMutation("features/microsoft_csp/workflows/save_permissions.py::save_selected_permissions");
  const applyPartnerWorkflow = useWorkflowMutation("features/microsoft_csp/workflows/apply_partner_permissions.py::apply_partner_permissions");
  const linkWorkflow = useWorkflowMutation("features/microsoft_csp/workflows/link_tenant.py::link_csp_tenant");
  const consentWorkflow = useWorkflowMutation("features/microsoft_csp/workflows/consent_tenant.py::consent_csp_tenant");
  const createOrgWorkflow = useWorkflowMutation("shared/bifrost/workflows/create_organization.py::create_organization");
  const createGdapWorkflow = useWorkflowMutation("features/microsoft_csp/workflows/create_gdap_relationship.py::create_gdap_relationship");
  const syncGdapWorkflow = useWorkflowMutation("features/microsoft_csp/workflows/update_gdap_assignments.py::update_gdap_assignments");
  const batchSyncGdapWorkflow = useWorkflowMutation("features/microsoft_csp/workflows/batch_update_gdap.py::batch_update_gdap");
  const seedTemplateWorkflow = useWorkflowMutation("features/microsoft_csp/workflows/seed_gdap_template.py::seed_gdap_template");

  // Local state seeded from query data (mutated locally by link/consent actions)
  const [tenants, setTenants] = useState<CspTenant[]>([]);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [permissionCounts, setPermissionCounts] = useState<PermissionCounts | null>(null);
  const [selectedPermissions, setSelectedPermissions] = useState<SelectedPermission[]>([]);
  const [availablePermissions, setAvailablePermissions] = useState<ApiPermissions[]>([]);
  const [gdapByTenant, setGdapByTenant] = useState<Record<string, GdapTenantStatus>>({});

  // UI state
  const [actionLoading, setActionLoading] = useState<Record<string, string>>({});
  const [actionSuccess, setActionSuccess] = useState<Record<string, boolean>>({});
  const [permissionDialogOpen, setPermissionDialogOpen] = useState(false);
  const [partnerDialogOpen, setPartnerDialogOpen] = useState(false);
  const [createOrgDialogOpen, setCreateOrgDialogOpen] = useState(false);
  const [createOrgTenant, setCreateOrgTenant] = useState<CspTenant | null>(null);
  const [applyResult, setApplyResult] = useState<any>(null);
  const [batchProgress, setBatchProgress] = useState<BatchConsentProgress | null>(null);
  const [gdapTemplateDialogOpen, setGdapTemplateDialogOpen] = useState(false);

  // Seed local state from query data
  useEffect(() => {
    if (tenantsWorkflow.data) {
      const result = tenantsWorkflow.data as any;
      setTenants(result.tenants || []);
      setOrganizations(result.organizations || []);
    }
  }, [tenantsWorkflow.data]);

  useEffect(() => {
    if (getPermissionsWorkflow.data) {
      const result = getPermissionsWorkflow.data as any;
      setPermissionCounts({
        delegated_count: result.delegated_count || 0,
        application_count: result.application_count || 0,
        total_count: result.total_count || 0,
      });
      setSelectedPermissions(result.permissions || []);
    }
  }, [getPermissionsWorkflow.data]);

  // Merge GDAP status into state
  useEffect(() => {
    if (gdapStatusWorkflow.data) {
      const result = gdapStatusWorkflow.data as any;
      setGdapByTenant(result.gdap_by_tenant || {});
    }
  }, [gdapStatusWorkflow.data]);

  // Merge GDAP status into tenant objects
  const tenantsWithGdap = useMemo(() => {
    return tenants.map((t) => {
      const gdap = gdapByTenant[t.tenant_id];
      return {
        ...t,
        gdap_status: (gdap?.status || "none") as CspTenant["gdap_status"],
        gdap_relationship_id: gdap?.relationship_id,
        gdap_approval_url: gdap?.approval_url,
        gdap_relationships: gdap?.relationships || [],
      };
    });
  }, [tenants, gdapByTenant]);

  // Derive read-only state directly from query data
  const setupStatus = checkSetupWorkflow.data as SetupStatus | undefined;

  // Handlers
  const handleRefreshAll = async () => {
    setActionLoading((prev) => ({ ...prev, "refresh-all": "refreshing" }));
    try {
      await Promise.all([
        checkSetupWorkflow.refetch(),
        getPermissionsWorkflow.refetch(),
        tenantsWorkflow.refetch(),
        gdapStatusWorkflow.refetch(),
      ]);
    } finally {
      setActionLoading((prev) => {
        const newState = { ...prev };
        delete newState["refresh-all"];
        return newState;
      });
    }
  };

  const handleConfigurePermissions = async () => {
    setPermissionDialogOpen(true);
    if (availablePermissions.length === 0) {
      try {
        const result = await listPermissionsWorkflow.execute();
        const data = result as any;
        setAvailablePermissions(data.apis || []);
      } catch (error) {
        console.error("Failed to load available permissions:", error);
      }
    }
  };

  const handleOpenPartnerDialog = () => {
    setPartnerDialogOpen(true);
  };

  const handleSavePermissions = async (permissions: SelectedPermission[]) => {
    await savePermissionsWorkflow.execute({ permissions });
    setPermissionDialogOpen(false);
    await getPermissionsWorkflow.refetch();
  };

  const handleApplyPartnerPermissions = async () => {
    setApplyResult(null);
    try {
      const result = await applyPartnerWorkflow.execute();
      setApplyResult(result);
    } catch (error) {
      setApplyResult({ success: false, errors: [{ error: String(error) }] });
    }
  };

  const handleLinkChange = async (tenant: CspTenant, orgId: string) => {
    const actionKey = `link-${tenant.tenant_id}`;
    setActionLoading((prev) => ({ ...prev, [actionKey]: "linking" }));

    try {
      if (orgId === "unlink") {
        await linkWorkflow.execute({
          tenant_id: tenant.tenant_id,
          tenant_name: tenant.tenant_name,
          domain: tenant.domain,
          customer_id: tenant.customer_id,
          org_id: null,
          org_name: null,
        });
        setTenants((prev) =>
          prev.map((t) =>
            t.tenant_id === tenant.tenant_id
              ? { ...t, bifrost_org_id: null, bifrost_org_name: null }
              : t
          )
        );
      } else {
        const selectedOrg = organizations.find((o) => o.value === orgId);
        if (selectedOrg) {
          await linkWorkflow.execute({
            tenant_id: tenant.tenant_id,
            tenant_name: tenant.tenant_name,
            domain: tenant.domain,
            customer_id: tenant.customer_id,
            org_id: selectedOrg.value,
            org_name: selectedOrg.label,
          });
          setTenants((prev) =>
            prev.map((t) =>
              t.tenant_id === tenant.tenant_id
                ? { ...t, bifrost_org_id: selectedOrg.value, bifrost_org_name: selectedOrg.label }
                : t
            )
          );
        }
      }
    } finally {
      setActionLoading((prev) => {
        const newState = { ...prev };
        delete newState[actionKey];
        return newState;
      });
    }
  };

  // Single handler for consent/refresh/retry - all call the same workflow
  const handleConsentAction = async (tenant: CspTenant, action: "consent" | "refresh" | "retry") => {
    const actionKey = `${action}-${tenant.tenant_id}`;
    const loadingText = action === "consent" ? "consenting" : action === "refresh" ? "refreshing" : "retrying";

    setActionLoading((prev) => ({ ...prev, [actionKey]: loadingText }));

    try {
      const result = await consentWorkflow.execute({ tenant_id: tenant.tenant_id }) as any;

      setTenants((prev) =>
        prev.map((t) =>
          t.tenant_id === tenant.tenant_id
            ? {
                ...t,
                consent_status: result.consent_status || "failed",
                consent_error: result.consent_error || undefined,
                consent_execution_id: consentWorkflow.executionId || t.consent_execution_id,
              }
            : t
        )
      );

      if (result.success || result.consent_status === "granted") {
        setActionSuccess((prev) => ({ ...prev, [actionKey]: true }));
        setTimeout(() => {
          setActionSuccess((prev) => {
            const newState = { ...prev };
            delete newState[actionKey];
            return newState;
          });
        }, 2000);
      }
    } catch (error) {
      setTenants((prev) =>
        prev.map((t) =>
          t.tenant_id === tenant.tenant_id
            ? { ...t, consent_status: "failed", consent_error: String(error) }
            : t
        )
      );
    } finally {
      setActionLoading((prev) => {
        const newState = { ...prev };
        delete newState[actionKey];
        return newState;
      });
    }
  };

  const handleConsent = (tenant: CspTenant) => handleConsentAction(tenant, "consent");
  const handleRefresh = (tenant: CspTenant) => handleConsentAction(tenant, "refresh");

  // GDAP handlers
  const handleCreateGdap = async (tenant: CspTenant) => {
    const actionKey = `gdap-create-${tenant.tenant_id}`;
    setActionLoading((prev) => ({ ...prev, [actionKey]: "creating" }));

    try {
      const result = await createGdapWorkflow.execute({
        tenant_id: tenant.tenant_id,
        tenant_name: tenant.tenant_name,
        domain: tenant.domain,
      }) as any;

      if (result.success !== false) {
        // Update local GDAP state
        setGdapByTenant((prev) => ({
          ...prev,
          [tenant.tenant_id]: {
            status: result.status || "approvalPending",
            relationship_id: result.relationship_id || "",
            display_name: result.display_name || "",
            approval_url: result.approval_url || null,
          },
        }));

        setActionSuccess((prev) => ({ ...prev, [actionKey]: true }));
        setTimeout(() => {
          setActionSuccess((prev) => {
            const newState = { ...prev };
            delete newState[actionKey];
            return newState;
          });
        }, 2000);
      }
    } catch (error) {
      console.error("Failed to create GDAP relationship:", error);
    } finally {
      setActionLoading((prev) => {
        const newState = { ...prev };
        delete newState[actionKey];
        return newState;
      });
    }
  };

  const handleSyncGdap = async (tenant: CspTenant) => {
    const actionKey = `gdap-sync-${tenant.tenant_id}`;
    setActionLoading((prev) => ({ ...prev, [actionKey]: "syncing" }));

    try {
      await syncGdapWorkflow.execute({
        tenant_id: tenant.tenant_id,
        tenant_name: tenant.tenant_name,
      });

      setActionSuccess((prev) => ({ ...prev, [actionKey]: true }));
      setTimeout(() => {
        setActionSuccess((prev) => {
          const newState = { ...prev };
          delete newState[actionKey];
          return newState;
        });
      }, 2000);
    } catch (error) {
      console.error("Failed to sync GDAP assignments:", error);
    } finally {
      setActionLoading((prev) => {
        const newState = { ...prev };
        delete newState[actionKey];
        return newState;
      });
    }
  };

  const handleCopyGdapLink = (tenant: CspTenant) => {
    if (tenant.gdap_approval_url) {
      navigator.clipboard.writeText(tenant.gdap_approval_url);
      const actionKey = `gdap-copy-${tenant.tenant_id}`;
      setActionSuccess((prev) => ({ ...prev, [actionKey]: true }));
      setTimeout(() => {
        setActionSuccess((prev) => {
          const newState = { ...prev };
          delete newState[actionKey];
          return newState;
        });
      }, 2000);
    }
  };

  const handleBatchSyncGdap = async () => {
    const actionKey = "gdap-batch-sync";
    setActionLoading((prev) => ({ ...prev, [actionKey]: "syncing" }));

    try {
      await batchSyncGdapWorkflow.execute();
      await gdapStatusWorkflow.refetch();

      setActionSuccess((prev) => ({ ...prev, [actionKey]: true }));
      setTimeout(() => {
        setActionSuccess((prev) => {
          const newState = { ...prev };
          delete newState[actionKey];
          return newState;
        });
      }, 2000);
    } catch (error) {
      console.error("Failed to batch sync GDAP:", error);
    } finally {
      setActionLoading((prev) => {
        const newState = { ...prev };
        delete newState[actionKey];
        return newState;
      });
    }
  };

  // Handler for opening create org dialog
  const handleCreateOrg = (tenant: CspTenant) => {
    setCreateOrgTenant(tenant);
    setCreateOrgDialogOpen(true);
  };

  // Handler for actually creating the org and linking it
  const handleCreateOrgSubmit = async (name: string, domain: string) => {
    if (!createOrgTenant) return;

    try {
      const result = await createOrgWorkflow.execute({ name, domain: domain || null }) as any;

      if (result?.success && result?.organization) {
        const newOrg = result.organization;

        setOrganizations((prev) => [
          ...prev,
          { label: newOrg.name, value: newOrg.id },
        ]);

        setCreateOrgDialogOpen(false);
        handleLinkChange(createOrgTenant, newOrg.id);

        setTenants((prev) =>
          prev.map((t) =>
            t.tenant_id === createOrgTenant.tenant_id
              ? { ...t, bifrost_org_id: newOrg.id, bifrost_org_name: newOrg.name }
              : t
          )
        );

        setCreateOrgTenant(null);
      }
    } catch (error) {
      console.error("Failed to create organization:", error);
    }
  };

  // Batch consent - simple sequential loop
  const handleBatchConsent = async (tenantsToConsent: CspTenant[]) => {
    if (tenantsToConsent.length === 0) return;

    for (let i = 0; i < tenantsToConsent.length; i++) {
      const tenant = tenantsToConsent[i];
      setBatchProgress({ total: tenantsToConsent.length, current: i + 1, currentTenantName: tenant.tenant_name });
      try {
        const result = await consentWorkflow.execute({ tenant_id: tenant.tenant_id }) as any;
        setTenants((prev) =>
          prev.map((t) =>
            t.tenant_id === tenant.tenant_id
              ? { ...t, consent_status: result.consent_status || "granted", consent_error: result.consent_error || undefined, consent_execution_id: consentWorkflow.executionId || t.consent_execution_id }
              : t
          )
        );
      } catch (error) {
        setTenants((prev) =>
          prev.map((t) =>
            t.tenant_id === tenant.tenant_id
              ? { ...t, consent_status: "failed", consent_error: String(error) }
              : t
          )
        );
      }
    }
    setBatchProgress(null);
  };

  // Computed state
  const integrationsConnected = setupStatus?.csp?.connected && setupStatus?.microsoft?.connected;
  const hasPermissions = (permissionCounts?.total_count ?? 0) > 0;
  const isLoading = checkSetupWorkflow.isLoading && !setupStatus;
  const isRefreshingAll = !!actionLoading["refresh-all"];

  // Consent should be disabled if setup is incomplete
  const consentDisabled = !integrationsConnected || !hasPermissions;

  if (isLoading) {
    return (
      <div className="flex flex-col h-full p-6 overflow-hidden">
        <div className="flex items-center justify-between mb-6">
          <div>
            <Skeleton className="h-9 w-64 mb-2" />
            <Skeleton className="h-5 w-96" />
          </div>
          <Skeleton className="h-10 w-32" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
        <Skeleton className="h-64 flex-1" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full p-6 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between mb-6 shrink-0">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Microsoft CSP</h1>
          <p className="text-muted-foreground mt-1">
            Manage CSP customer tenants, GDAP relationships, and application consent.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setGdapTemplateDialogOpen(true)}
          >
            <Settings className="w-4 h-4 mr-2" />
            GDAP Template
          </Button>
          <Button
            variant="outline"
            onClick={handleRefreshAll}
            disabled={isRefreshingAll}
          >
            {isRefreshingAll ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4 mr-2" />
            )}
            Refresh
          </Button>
        </div>
      </div>

      {/* Status Cards */}
      <SetupStatusCards
        setupStatus={setupStatus || null}
        permissionCounts={permissionCounts}
        loading={checkSetupWorkflow.isLoading}
        onConfigurePermissions={handleConfigurePermissions}
        onApplyToPartner={handleOpenPartnerDialog}
      />

      {/* Tenant Table */}
      <Card className="flex flex-col min-h-0 flex-1">
        <CardHeader className="shrink-0 pb-4">
          <CardTitle className="flex items-center gap-2">
            <Building2 className="w-5 h-5" />
            CSP Customers
          </CardTitle>
          <CardDescription>
            Link tenants to Bifrost organizations, manage GDAP relationships, and grant consent.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex-1 min-h-0 overflow-hidden">
          <TenantTable
            tenants={tenantsWithGdap}
            organizations={organizations}
            loading={tenantsWorkflow.isLoading && !tenantsWorkflow.data}
            onLinkChange={handleLinkChange}
            onCreateOrg={handleCreateOrg}
            onConsent={handleConsent}
            onBatchConsent={handleBatchConsent}
            onRefresh={handleRefresh}
            onCreateGdap={handleCreateGdap}
            onSyncGdap={handleSyncGdap}
            onCopyGdapLink={handleCopyGdapLink}
            onBatchSyncGdap={handleBatchSyncGdap}
            actionLoading={actionLoading}
            actionSuccess={actionSuccess}
            consentDisabled={consentDisabled}
            batchProgress={batchProgress}
          />
        </CardContent>
      </Card>

      {/* Permission Dialog */}
      <PermissionDialog
        open={permissionDialogOpen}
        onOpenChange={setPermissionDialogOpen}
        availablePermissions={availablePermissions}
        selectedPermissions={selectedPermissions}
        onSave={handleSavePermissions}
        loading={listPermissionsWorkflow.isLoading}
        saving={savePermissionsWorkflow.isLoading}
      />

      {/* Partner Setup Dialog */}
      <PartnerSetupDialog
        open={partnerDialogOpen}
        onOpenChange={setPartnerDialogOpen}
        applicationCount={permissionCounts?.application_count ?? 0}
        onApplyPermissions={handleApplyPartnerPermissions}
        applyLoading={applyPartnerWorkflow.isLoading}
        applyResult={applyResult}
      />

      {/* Create Organization Dialog */}
      <CreateOrgDialog
        open={createOrgDialogOpen}
        onOpenChange={setCreateOrgDialogOpen}
        tenantName={createOrgTenant?.tenant_name || ""}
        tenantDomain={createOrgTenant?.domain || ""}
        onCreate={handleCreateOrgSubmit}
        creating={createOrgWorkflow.isLoading}
      />

      {/* GDAP Template Dialog */}
      <GdapTemplateDialog
        open={gdapTemplateDialogOpen}
        onOpenChange={setGdapTemplateDialogOpen}
        tenants={tenantsWithGdap}
        onSeedTemplate={async (relationshipId: string) => {
          await seedTemplateWorkflow.execute({ relationship_id: relationshipId });
        }}
        seeding={seedTemplateWorkflow.isLoading}
      />
    </div>
  );
}
