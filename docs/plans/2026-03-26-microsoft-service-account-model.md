## Microsoft Service Account Model

This note records the recommended operating model for the `Microsoft` and
`Microsoft CSP` integrations in Bifrost.

### Recommendation

Use a dedicated Bifrost Entra application as the long-lived Microsoft runtime
identity, and keep partner-side delegated access separate.

In practical terms:

- `Microsoft CSP` should be the delegated partner-admin connection
- `Microsoft` should be the dedicated Bifrost application identity

This is intentionally closer to the security model used by CIPP than to a
human-admin-login model.

### Why This Model Fits

The Microsoft integration family serves two different purposes:

- partner operations: tenant discovery, GDAP, consent, Partner Center
- customer-tenant runtime access: Graph and Exchange work after consent

Trying to force both through one delegated user login makes the system harder
to reason about and widens blast radius. A dedicated application identity keeps
runtime access stable and auditable, while the delegated partner connection can
stay focused on onboarding and consent workflows.

### Intended Identity Split

#### Microsoft CSP

`Microsoft CSP` is the partner-side delegated identity.

Use it for:

- Partner Center customer enumeration
- GDAP relationship creation and updates
- customer consent flows
- tenant linking and relationship management

Operationally, this integration requires interactive OAuth and a stored refresh
token.

#### Microsoft

`Microsoft` is the Bifrost runtime application identity.

Use it for:

- Microsoft Graph operations in customer tenants
- Exchange Online operations in customer tenants
- customer-tenant app-permission execution after consent

Operationally, this integration should be a dedicated multi-tenant Entra app
with explicit application credentials.

### Service Principal Guidance

The `Microsoft` integration should be modeled as a dedicated service principal,
not as a technician's account.

Recommended posture:

- use a dedicated Bifrost app registration
- keep the app multi-tenant if customer consent is part of the workflow
- prefer certificate authentication long-term
- accept client secret initially if needed to unblock deployment
- do not rely on a human mailbox or day-to-day admin account as the runtime
  identity

### Comparison To CIPP

This should look conceptually similar to CIPP:

- a controlled app identity performs the steady-state work
- a partner/admin setup path handles onboarding and tenant-wide approval
- permissions are curated and explicit
- operators reason about the app as infrastructure, not as a human account

What should *not* happen:

- treating `Microsoft CSP` as the only Microsoft identity
- using a human Global Admin login as the normal runtime principal
- granting broad permissions just because delegated partner access exists

### Permission Strategy

Start with the smallest workable application-permission set for the Bifrost app.

Guidelines:

- grant only the Graph and Exchange permissions Bifrost actually uses
- separate onboarding permissions from day-to-day runtime permissions when
  possible
- use partner delegated access only for setup and consent paths
- review requested permissions as part of app rollout, not ad hoc during an
  incident

### Operational Sequence

1. Configure `Microsoft CSP` with delegated partner OAuth.
2. Configure `Microsoft` as the dedicated Bifrost Entra application.
3. Link customer tenants through the CSP app.
4. Grant customer consent to the `Microsoft` application.
5. Run customer-tenant workflows through `Microsoft`, not through the partner
   delegated token.

### Current Constraint

As of this note:

- `Microsoft` can be configured as the dedicated app identity
- `Microsoft CSP` still requires an interactive OAuth reconnect to obtain a
  refresh token before the Partner Center and GDAP workflows can run fully

### Design Rule

When in doubt:

- ask whether the action is a partner setup / consent task
- or a customer-tenant runtime task

If it is partner setup, it belongs to `Microsoft CSP`.
If it is customer runtime access, it should run through `Microsoft`.
