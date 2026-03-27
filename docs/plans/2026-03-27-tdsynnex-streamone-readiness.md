## TD SYNNEX StreamOne ION integration readiness

### Summary

TD SYNNEX's public `StreamOne ION` API is workable for cloud and subscription order lifecycle workflows, but it is not yet a clean fit for Bifrost's current integration runtime.

This note applies specifically to `StreamOne ION`, not the separate
`TD SYNNEX Partner API` described in
`/home/thomas/mtg-bifrost/bifrost/docs/plans/2026-03-27-tdsynnex-partner-api-readiness.md`.

The main problem is authentication:

- StreamOne ION uses `POST https://ion.tdsynnex.com/oauth/token`
- access tokens are minted from a `refresh_token`
- the docs state the returned `refresh_token` is rotated and the prior one expires after use

Bifrost integrations can read integration config, but current workflow code does not have a first-class way to persist a rotated integration secret back into that integration config. That makes a straightforward TD SYNNEX client brittle across workflow executions.

### What the public API does support

Public StreamOne ION docs are good enough to confirm these cloud-order surfaces:

- `GET /accounts/{accountId}/customers?pageSize=...`
- `GET /accounts/{accountId}/customers/{customerId}`
- `GET /accounts/{accountId}/orders`
- `GET /accounts/{accountId}/customers/{customerId}/orders`
- `GET /accounts/{accountId}/customers/{customerId}/orders/{orderId}`
- `POST /accounts/{accountId}/customers/{customerId}/orders/{orderId}:cancel`

For Bifrost, that means TD SYNNEX is a credible future integration for:

- customer discovery and mapping
- cloud order reconciliation
- normalized order lifecycle events such as `order_confirmed`, `order_completed`, `order_canceled`, and `order_exception`

### What the public API does not clearly provide

From the public docs currently available, I do not see a comparable physical-order shipment and delivery API for classic distribution orders. The strongest documented surface is StreamOne ION cloud ordering.

So the current public posture is:

- `StreamOne / cloud orders`: workable
- `physical shipment notices / parcel tracking / delivery events`: not verified from public API material

### Why this is not a clean scaffold today

The auth model creates a runtime mismatch with Bifrost:

1. Bifrost reads integration secrets from stored integration config.
2. TD SYNNEX rotates the `refresh_token` during token exchange.
3. The new `refresh_token` needs to be saved somewhere durable.
4. Current integration helpers do not provide a clean integration-config write-back path for that rotated secret.

Without that write-back, a TD SYNNEX integration would work once and then drift into auth failure on the next execution after token rotation.

### Recommended path

Do not commit a full TD SYNNEX integration yet.

Instead:

1. Keep TD SYNNEX on the shortlist as a `StreamOne ION` cloud-order integration.
2. Add platform support for rotating integration secret persistence, or a dedicated OAuth-style refresh-token store for nonstandard token flows.
3. Once that exists, implement the integration around:
   - global config: `account_id`, `refresh_token`
   - org mapping entity: `customer_id`
   - primary workflows:
     - list customers
     - sync customers
     - list account orders
     - list customer orders
     - get order
     - cancel order

### Interim option if urgently needed

If Midtown needs TD SYNNEX before platform support exists, the least bad workaround is:

- manually maintain a current refresh token outside Bifrost
- or inject short-lived access tokens operationally

That is operationally fragile and should be treated as a stopgap only.

### Sources

- StreamOne ION Partner API reference: `https://docs.streamone.cloud/`
- Local research note: `/home/thomas/agents/integrations/tdsynnex/README.md`
