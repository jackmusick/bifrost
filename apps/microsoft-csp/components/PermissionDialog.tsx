// Permission configuration dialog for selecting delegated and application permissions

interface Permission {
  id: string;
  name: string;
  description: string;
  admin_consent_required?: boolean;
}

interface ApiPermissions {
  api_id: string;
  api_name: string;
  display_name: string;
  delegated_permissions: Permission[];
  application_permissions: Permission[];
}

interface SelectedPermission {
  api_id: string;
  api_name: string;
  permission_name: string;
  permission_type: "delegated" | "application";
  required?: boolean;
}

interface PermissionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  availablePermissions: ApiPermissions[];
  selectedPermissions: SelectedPermission[];
  onSave: (permissions: SelectedPermission[]) => void;
  loading: boolean;
  saving: boolean;
}

// Required bootstrap permissions - always included
const REQUIRED_PERMISSIONS = [
  { api_id: "00000003-0000-0000-c000-000000000000", name: "Directory.ReadWrite.All", type: "delegated" },
  { api_id: "00000003-0000-0000-c000-000000000000", name: "AppRoleAssignment.ReadWrite.All", type: "delegated" },
];

// Exchange Online API ID - application permissions not supported (requires directory role)
const EXCHANGE_API_ID = "00000002-0000-0ff1-ce00-000000000000";

function isRequired(apiId: string, permName: string, permType: string): boolean {
  return REQUIRED_PERMISSIONS.some(
    (r) => r.api_id === apiId && r.name === permName && r.type === permType
  );
}

export function PermissionDialog({
  open,
  onOpenChange,
  availablePermissions,
  selectedPermissions,
  onSave,
  loading,
  saving,
}: PermissionDialogProps) {
  const [localSelection, setLocalSelection] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState("");
  const [activeTab, setActiveTab] = useState<string>(
    availablePermissions[0]?.api_id || "00000003-0000-0000-c000-000000000000"
  );

  // Initialize local selection from props
  useEffect(() => {
    if (open) {
      const selected = new Set<string>();
      selectedPermissions.forEach((p) => {
        selected.add(`${p.api_id}:${p.permission_name}:${p.permission_type}`);
      });
      // Always include required permissions
      REQUIRED_PERMISSIONS.forEach((r) => {
        selected.add(`${r.api_id}:${r.name}:${r.type}`);
      });
      setLocalSelection(selected);
    }
  }, [open, selectedPermissions]);

  // Update active tab when permissions load
  useEffect(() => {
    if (availablePermissions.length > 0 && !availablePermissions.find(a => a.api_id === activeTab)) {
      setActiveTab(availablePermissions[0].api_id);
    }
  }, [availablePermissions]);

  const togglePermission = (apiId: string, apiName: string, permName: string, permType: "delegated" | "application") => {
    const key = `${apiId}:${permName}:${permType}`;
    
    // Don't allow toggling required permissions
    if (isRequired(apiId, permName, permType)) {
      return;
    }

    setLocalSelection((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const handleSave = () => {
    const permissions: SelectedPermission[] = [];
    localSelection.forEach((key) => {
      const [apiId, permName, permType] = key.split(":");
      const api = availablePermissions.find((a) => a.api_id === apiId);
      permissions.push({
        api_id: apiId,
        api_name: api?.api_name || apiId,
        permission_name: permName,
        permission_type: permType as "delegated" | "application",
        required: isRequired(apiId, permName, permType),
      });
    });
    onSave(permissions);
  };

  const activeApi = availablePermissions.find((a) => a.api_id === activeTab);

  const filterPermissions = (perms: Permission[]) => {
    if (!searchQuery.trim()) return perms;
    const query = searchQuery.toLowerCase();
    return perms.filter(
      (p) =>
        p.name.toLowerCase().includes(query) ||
        p.description.toLowerCase().includes(query)
    );
  };

  const delegatedCount = Array.from(localSelection).filter((k) => k.endsWith(":delegated")).length;
  const applicationCount = Array.from(localSelection).filter((k) => k.endsWith(":application")).length;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Configure Permissions</DialogTitle>
          <DialogDescription>
            Select the permissions to grant when onboarding customer tenants.
            Required permissions cannot be deselected.
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="flex-1 min-h-0 flex flex-col">
            {/* Search and summary */}
            <div className="flex items-center justify-between mb-4">
              <div className="relative flex-1 max-w-sm">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  placeholder="Search permissions..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  style={{ paddingLeft: "2.5rem" }}
                />
              </div>
              <div className="text-sm text-muted-foreground">
                {delegatedCount} delegated, {applicationCount} application selected
              </div>
            </div>

            {/* API Tabs */}
            <Tabs value={activeTab} onValueChange={setActiveTab}>
              <TabsList className="w-full justify-start">
                {availablePermissions.map((api) => (
                  <TabsTrigger key={api.api_id} value={api.api_id} className="text-xs">
                    {api.api_name}
                  </TabsTrigger>
                ))}
              </TabsList>

              {availablePermissions.map((api) => (
                <TabsContent
                  key={api.api_id}
                  value={api.api_id}
                  className="mt-4"
                >
                  <div className="grid grid-cols-2 gap-4">
                    {/* Delegated Permissions */}
                    <div className="flex flex-col">
                      <h4 className="font-medium text-sm mb-2 flex items-center gap-2">
                        <Users className="w-4 h-4" />
                        Delegated Permissions
                        <span className="text-xs text-muted-foreground font-normal">
                          (acts as user)
                        </span>
                      </h4>
                      <div className="h-[400px] overflow-auto border rounded-lg">
                        {filterPermissions(api.delegated_permissions).length === 0 ? (
                          <div className="p-4 text-sm text-muted-foreground text-center">
                            No matching permissions
                          </div>
                        ) : (
                          <div className="divide-y">
                            {filterPermissions(api.delegated_permissions).map((perm) => {
                              const key = `${api.api_id}:${perm.name}:delegated`;
                              const isSelected = localSelection.has(key);
                              const required = isRequired(api.api_id, perm.name, "delegated");

                              return (
                                <label
                                  key={perm.id}
                                  className={`flex items-start gap-3 p-3 hover:bg-muted/50 cursor-pointer ${
                                    required ? "bg-blue-500/5" : ""
                                  }`}
                                >
                                  <Checkbox
                                    checked={isSelected}
                                    onCheckedChange={() =>
                                      togglePermission(api.api_id, api.api_name, perm.name, "delegated")
                                    }
                                    disabled={required}
                                    className="mt-0.5"
                                  />
                                  <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2">
                                      <span className="text-sm font-medium truncate">{perm.name}</span>
                                      {required && (
                                        <Badge variant="secondary" className="text-xs">Required</Badge>
                                      )}
                                      {perm.admin_consent_required && (
                                        <Badge variant="outline" className="text-xs">Admin</Badge>
                                      )}
                                    </div>
                                    <p className="text-xs text-muted-foreground line-clamp-2">
                                      {perm.description}
                                    </p>
                                  </div>
                                </label>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Application Permissions */}
                    <div className="flex flex-col">
                      <h4 className="font-medium text-sm mb-2 flex items-center gap-2">
                        <Shield className="w-4 h-4" />
                        Application Permissions
                        <span className="text-xs text-muted-foreground font-normal">
                          (acts as app)
                        </span>
                      </h4>
                      <div className="h-[400px] overflow-auto border rounded-lg">
                        {api.api_id === EXCHANGE_API_ID ? (
                          <div className="p-4 text-sm text-muted-foreground text-center flex flex-col items-center justify-center h-full">
                            <AlertTriangle className="w-8 h-8 mb-2 text-yellow-500" />
                            <p className="font-medium text-foreground">Not Available</p>
                            <p className="mt-1">
                              Exchange application permissions require a directory role assignment
                              which is not supported via GDAP. Use delegated permissions instead.
                            </p>
                          </div>
                        ) : filterPermissions(api.application_permissions).length === 0 ? (
                          <div className="p-4 text-sm text-muted-foreground text-center">
                            No matching permissions
                          </div>
                        ) : (
                          <div className="divide-y">
                            {filterPermissions(api.application_permissions).map((perm) => {
                              const key = `${api.api_id}:${perm.name}:application`;
                              const isSelected = localSelection.has(key);
                              const required = isRequired(api.api_id, perm.name, "application");

                              return (
                                <label
                                  key={perm.id}
                                  className={`flex items-start gap-3 p-3 hover:bg-muted/50 cursor-pointer ${
                                    required ? "bg-blue-500/5" : ""
                                  }`}
                                >
                                  <Checkbox
                                    checked={isSelected}
                                    onCheckedChange={() =>
                                      togglePermission(api.api_id, api.api_name, perm.name, "application")
                                    }
                                    disabled={required}
                                    className="mt-0.5"
                                  />
                                  <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2">
                                      <span className="text-sm font-medium truncate">{perm.name}</span>
                                      {required && (
                                        <Badge variant="secondary" className="text-xs">Required</Badge>
                                      )}
                                    </div>
                                    <p className="text-xs text-muted-foreground line-clamp-2">
                                      {perm.description}
                                    </p>
                                  </div>
                                </label>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </TabsContent>
              ))}
            </Tabs>
          </div>
        )}

        <DialogFooter className="mt-4">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={saving || loading}>
            {saving ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Check className="w-4 h-4 mr-2" />
                Save Permissions
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
