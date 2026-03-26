// GDAP Template management dialog — seed template from a specific relationship

interface GdapRelationship {
  id: string;
  display_name: string;
  status: string;
}

interface CspTenant {
  tenant_id: string;
  tenant_name: string;
  domain: string;
  gdap_status?: string;
  gdap_relationship_id?: string;
  gdap_relationships?: GdapRelationship[];
}

interface GdapTemplateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  tenants: CspTenant[];
  onSeedTemplate: (relationshipId: string) => Promise<void>;
  seeding: boolean;
}

export function GdapTemplateDialog({
  open,
  onOpenChange,
  tenants,
  onSeedTemplate,
  seeding,
}: GdapTemplateDialogProps) {
  const [selectedTenantId, setSelectedTenantId] = useState("");
  const [selectedRelationshipId, setSelectedRelationshipId] = useState("");
  const [seedSuccess, setSeedSuccess] = useState(false);

  // Tenants with any GDAP relationships
  const tenantsWithRelationships = useMemo(() => {
    return tenants.filter((t) => t.gdap_relationships && t.gdap_relationships.length > 0);
  }, [tenants]);

  const tenantOptions = useMemo(() => {
    return tenantsWithRelationships.map((t) => ({
      value: t.tenant_id,
      label: `${t.tenant_name} (${t.domain})`,
    }));
  }, [tenantsWithRelationships]);

  // Active relationships for the selected tenant
  const availableRelationships = useMemo(() => {
    if (!selectedTenantId) return [];
    const tenant = tenants.find((t) => t.tenant_id === selectedTenantId);
    if (!tenant?.gdap_relationships) return [];
    return tenant.gdap_relationships.filter((r) => r.status === "active");
  }, [tenants, selectedTenantId]);

  const relationshipOptions = useMemo(() => {
    return availableRelationships.map((r) => ({
      value: r.id,
      label: r.display_name || r.id,
    }));
  }, [availableRelationships]);

  // Reset relationship when tenant changes
  const handleTenantChange = (tenantId: string) => {
    setSelectedTenantId(tenantId);
    setSelectedRelationshipId("");
    setSeedSuccess(false);
  };

  const handleSeed = async () => {
    if (!selectedRelationshipId) return;
    setSeedSuccess(false);
    try {
      await onSeedTemplate(selectedRelationshipId);
      setSeedSuccess(true);
      setTimeout(() => setSeedSuccess(false), 3000);
    } catch (error) {
      console.error("Failed to seed template:", error);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Shield className="w-5 h-5" />
            GDAP Template
          </DialogTitle>
          <DialogDescription>
            Seed the GDAP template from a specific relationship. Select the tenant, then choose which
            relationship to copy security group and role assignments from.
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 min-h-0 flex flex-col gap-6 py-4">
          {/* Step 1: Select tenant */}
          <div className="space-y-3">
            <h4 className="text-sm font-medium">1. Select Tenant</h4>
            <Combobox
              options={tenantOptions}
              value={selectedTenantId}
              onValueChange={handleTenantChange}
              placeholder="Select a tenant with GDAP relationships..."
              searchPlaceholder="Search tenants..."
              emptyText={tenantsWithRelationships.length === 0
                ? "No tenants with GDAP relationships"
                : "No matching tenant found."}
            />
          </div>

          {/* Step 2: Select relationship */}
          {selectedTenantId && (
            <div className="space-y-3">
              <h4 className="text-sm font-medium">2. Select Relationship</h4>
              {availableRelationships.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No active relationships for this tenant.
                </p>
              ) : (
                <Combobox
                  options={relationshipOptions}
                  value={selectedRelationshipId}
                  onValueChange={setSelectedRelationshipId}
                  placeholder="Select a relationship..."
                  searchPlaceholder="Search relationships..."
                  emptyText="No matching relationship found."
                />
              )}
            </div>
          )}

          {/* Seed button */}
          {selectedRelationshipId && (
            <div>
              <Button
                onClick={handleSeed}
                disabled={seeding}
                variant={seedSuccess ? "default" : "outline"}
                className={seedSuccess ? "bg-green-600 hover:bg-green-700" : ""}
              >
                {seeding ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Seeding...
                  </>
                ) : seedSuccess ? (
                  <>
                    <Check className="w-4 h-4 mr-2" />
                    Seeded
                  </>
                ) : (
                  <>
                    <Download className="w-4 h-4 mr-2" />
                    Seed Template
                  </>
                )}
              </Button>
            </div>
          )}

          <Separator />

          {/* Info */}
          <div className="space-y-3">
            <h4 className="text-sm font-medium">How It Works</h4>
            <div className="text-sm text-muted-foreground space-y-2">
              <p>
                Seeding copies the security group to role mappings from the selected
                relationship into the template table.
              </p>
              <p>
                New GDAP relationships created via "Create GDAP" will use all roles from the template.
                "Sync Roles" will update existing relationships to match the template's group assignments.
              </p>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
