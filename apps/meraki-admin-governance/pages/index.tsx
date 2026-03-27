const WORKFLOW_IDS = {
  getPolicy: "ae3cb1e2-e78e-4ab1-bee1-4f61b13bb028",
  savePolicy: "e391174e-b341-423d-bcd5-81e56c5e809d",
  auditBaseline: "8b7cbc91-4b8d-40fd-9ea1-55d9dbf2dd4f",
  auditProcurement: "8bc2ea7c-7c36-41ef-b026-0e6c28c7476c",
  listOrgNames: "52faaf0d-b861-407a-920a-ee33de7a6af3",
  listAdminOptions: "c2e69d39-d5e1-478f-b823-4b4815a78876",
} as const;

export default function MerakiAdminGovernancePage() {
  const policyQuery = useWorkflowQuery(WORKFLOW_IDS.getPolicy);
  const orgOptionsQuery = useWorkflowQuery(WORKFLOW_IDS.listOrgNames);
  const adminOptionsQuery = useWorkflowQuery(WORKFLOW_IDS.listAdminOptions);
  const savePolicy = useWorkflowMutation(WORKFLOW_IDS.savePolicy);
  const auditBaseline = useWorkflowMutation(WORKFLOW_IDS.auditBaseline);
  const auditProcurement = useWorkflowMutation(WORKFLOW_IDS.auditProcurement);

  const [customerExclusions, setCustomerExclusions] = useState<string[]>([]);
  const [procurementOrgs, setProcurementOrgs] = useState<string[]>([]);
  const [procurementAdmins, setProcurementAdmins] = useState<string[]>([]);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!policyQuery.data) return;
    setCustomerExclusions(policyQuery.data.customer_org_exclusions || []);
    setProcurementOrgs(policyQuery.data.procurement_org_names || []);
    setProcurementAdmins(policyQuery.data.procurement_allowed_admin_emails || []);
  }, [policyQuery.data]);

  const handleSave = async () => {
    setSaveMessage(null);
    await savePolicy.execute({
      customer_org_exclusions_csv: customerExclusions.join(","),
      procurement_org_names_csv: procurementOrgs.join(","),
      procurement_allowed_admin_emails_csv: procurementAdmins.join(","),
    });
    await policyQuery.refetch();
    setSaveMessage("Policy saved.");
  };

  const renderAudit = (title: string, audit: typeof auditBaseline) => {
    const result = audit.data;
    return (
      <section className="meraki-governance__section">
        <div className="meraki-governance__section-header">
          <h3 className="meraki-governance__section-title">{title}</h3>
          <button
            className="meraki-governance__button"
            onClick={() => void audit.execute()}
            disabled={audit.isLoading}
          >
            {audit.isLoading ? "Running..." : "Run Audit"}
          </button>
        </div>
        {audit.error && <p className="meraki-governance__error">{audit.error}</p>}
        {!result && !audit.isLoading && (
          <p className="meraki-governance__muted">No audit run yet.</p>
        )}
        {result && (
          <div className="meraki-governance__result-block">
            <p className="meraki-governance__summary">
              Organizations with disparities:{" "}
              <strong>{result.organizations_with_disparities}</strong>
            </p>
            {result.disparities.length === 0 ? (
              <p className="meraki-governance__muted">No disparities.</p>
            ) : (
              <div className="meraki-governance__table">
                {result.disparities.map((item: any) => (
                  <div
                    key={item.organization_name}
                    className="meraki-governance__row"
                  >
                    <div className="meraki-governance__org-name">
                      {item.organization_name}
                    </div>
                    <div className="meraki-governance__detail">
                      Missing:{" "}
                      {item.missing_admins.length > 0
                        ? item.missing_admins.join(", ")
                        : "none"}
                    </div>
                    <div className="meraki-governance__detail">
                      Extra:{" "}
                      {item.extra_admins.length > 0
                        ? item.extra_admins.join(", ")
                        : "none"}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </section>
    );
  };

  return (
    <div className="meraki-governance">
      <div className="meraki-governance__hero">
        <div>
          <h1 className="meraki-governance__title">Meraki Admin Governance</h1>
          <p className="meraki-governance__subtitle">
            Store the Meraki admin policy here, then let the reusable workflows
            read it. Workflow parameters stay for one-off overrides, but the
            persistent policy lives in Bifrost config.
          </p>
        </div>
        <button
          className="meraki-governance__button meraki-governance__button--secondary"
          onClick={() => void policyQuery.refetch()}
          disabled={policyQuery.isLoading}
        >
          Refresh Policy
        </button>
      </div>

      <section className="meraki-governance__section">
        <h2 className="meraki-governance__section-title">Configuration</h2>
        {policyQuery.error && (
          <p className="meraki-governance__error">{policyQuery.error}</p>
        )}
        <div className="meraki-governance__field-grid">
          <label className="meraki-governance__field">
            <span className="meraki-governance__label">
              Customer Org Exclusions
            </span>
            <MultiCombobox
              options={orgOptionsQuery.data || []}
              value={customerExclusions}
              onValueChange={setCustomerExclusions}
              placeholder="Select excluded orgs..."
              searchPlaceholder="Search Meraki orgs..."
              emptyText="No Meraki org found."
              isLoading={orgOptionsQuery.isLoading}
            />
          </label>
          <label className="meraki-governance__field">
            <span className="meraki-governance__label">
              Procurement License Orgs
            </span>
            <MultiCombobox
              options={orgOptionsQuery.data || []}
              value={procurementOrgs}
              onValueChange={setProcurementOrgs}
              placeholder="Select procurement/license orgs..."
              searchPlaceholder="Search Meraki orgs..."
              emptyText="No Meraki org found."
              isLoading={orgOptionsQuery.isLoading}
            />
          </label>
          <label className="meraki-governance__field">
            <span className="meraki-governance__label">
              Procurement Allowed Admins
            </span>
            <MultiCombobox
              options={adminOptionsQuery.data || []}
              value={procurementAdmins}
              onValueChange={setProcurementAdmins}
              placeholder="Select allowed admins..."
              searchPlaceholder="Search baseline admins..."
              emptyText="No Meraki admin found."
              isLoading={adminOptionsQuery.isLoading}
            />
          </label>
        </div>
        <div className="meraki-governance__action-row">
          <button
            className="meraki-governance__button"
            onClick={() => void handleSave()}
            disabled={savePolicy.isLoading}
          >
            {savePolicy.isLoading ? "Saving..." : "Save Policy"}
          </button>
          {saveMessage && (
            <span className="meraki-governance__success">{saveMessage}</span>
          )}
        </div>
      </section>

      <div className="meraki-governance__audit-grid">
        {renderAudit("Baseline Audit", auditBaseline)}
        {renderAudit("Procurement Audit", auditProcurement)}
      </div>
    </div>
  );
}
