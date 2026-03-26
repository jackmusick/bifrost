## Microsoft Integration Boundaries

This note documents the intended boundary between the `Microsoft CSP` and
`Microsoft` integrations so operators do not treat them as duplicates.

### Mental Model

- `Microsoft CSP` is the partner-side delegated identity.
- `Microsoft` is the customer-tenant application identity.

In practical terms:

- `Microsoft CSP` answers: "Who are we as the partner?"
- `Microsoft` answers: "What app are we asking customer tenants to trust?"

### Microsoft CSP

`Microsoft CSP` is the delegated Partner Center and GDAP integration.

It is used for:

- listing CSP customers from Partner Center
- linking CSP tenants to Bifrost organizations
- driving GDAP and consent workflows
- performing delegated token exchange into customer tenants

Operationally, this integration requires an interactive OAuth connection and a
stored refresh token. If it is not authenticated, the CSP management app can
see the framework but cannot enumerate customers or perform consent.

### Microsoft

`Microsoft` is the Bifrost application identity used for customer-tenant API
access after a tenant has been linked and consented.

It is used for:

- Microsoft Graph access in customer tenants
- Exchange Online access in customer tenants
- application permission rollout driven by the CSP app

Operationally, this integration is modeled as client credentials. It should
have a real `client_id` and `client_secret`, and its tenant context is resolved
through org mapping and linked tenant metadata.

### How They Work Together

The intended sequence is:

1. Connect `Microsoft CSP` with delegated partner OAuth.
2. Configure `Microsoft` with the Bifrost multi-tenant app credentials.
3. Use the CSP app to list partner customers.
4. Link a customer tenant to a Bifrost organization.
5. Use delegated CSP access to grant or refresh consent for the `Microsoft`
   application in that tenant.
6. Use the `Microsoft` integration for customer-tenant Graph and Exchange work.

If `Microsoft` is configured but `Microsoft CSP` is not authenticated, the app
is only half ready. The reverse is also incomplete: `Microsoft CSP` can see
customers, but there is no application identity to consent.

### Operator Guidance

- Do not model `Microsoft CSP` as the customer app.
- Do not model `Microsoft` as the partner admin connection.
- Expect the CSP management app to require both integrations.
- When troubleshooting, check them independently:
  - `Microsoft CSP`: delegated OAuth / refresh token
  - `Microsoft`: client credentials / app identity

### Current UI Language

The Microsoft CSP app should describe these integrations as:

- `Microsoft CSP`: Partner Center and GDAP delegated access
- `Microsoft`: Customer-tenant application identity

For the recommended security posture and operator model, see also:

- `docs/plans/2026-03-26-microsoft-service-account-model.md`
