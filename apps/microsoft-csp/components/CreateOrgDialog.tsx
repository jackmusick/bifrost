// Dialog for creating a new Bifrost organization from a CSP tenant

interface CreateOrgDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  tenantName: string;
  tenantDomain: string;
  onCreate: (name: string, domain: string) => void;
  creating: boolean;
}

export function CreateOrgDialog({
  open,
  onOpenChange,
  tenantName,
  tenantDomain,
  onCreate,
  creating,
}: CreateOrgDialogProps) {
  const [orgName, setOrgName] = useState(tenantName);
  const [orgDomain, setOrgDomain] = useState("");

  // Reset form when dialog opens with new tenant
  useEffect(() => {
    if (open) {
      setOrgName(tenantName);
      // Use tenant domain, but skip onmicrosoft.com domains
      const domain = tenantDomain.toLowerCase();
      if (!domain.includes("onmicrosoft.com")) {
        setOrgDomain(domain);
      } else {
        setOrgDomain("");
      }
    }
  }, [open, tenantName, tenantDomain]);

  const handleCreate = () => {
    if (!orgName.trim()) return;
    onCreate(orgName.trim(), orgDomain.trim());
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Create Bifrost Organization</DialogTitle>
          <DialogDescription>
            Create a new organization and link it to this CSP tenant.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="org-name">Organization Name</Label>
            <Input
              id="org-name"
              value={orgName}
              onChange={(e) => setOrgName(e.target.value)}
              placeholder="Enter organization name"
              disabled={creating}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="org-domain">Domain (optional)</Label>
            <Input
              id="org-domain"
              value={orgDomain}
              onChange={(e) => setOrgDomain(e.target.value)}
              placeholder="e.g., acme.com"
              disabled={creating}
            />
            <p className="text-xs text-muted-foreground">
              The primary domain for this organization.
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={creating}>
            Cancel
          </Button>
          <Button onClick={handleCreate} disabled={creating || !orgName.trim()}>
            {creating ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Creating...
              </>
            ) : (
              <>
                <Plus className="w-4 h-4 mr-2" />
                Create Organization
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
