## TD SYNNEX Partner API integration note

### Summary

`/home/thomas/agents/landing/synnex-openapi.json` materially changes the TD SYNNEX outlook for Bifrost.

This spec is not `StreamOne ION`. It is a separate `TD SYNNEX Partner API`
with a much cleaner fit for Midtown's procurement visibility goals:

- OAuth token exchange is plain `client_credentials`
- endpoints are reseller lookup APIs for:
  - order details
  - shipment details
  - invoice details
  - quote status

That makes it a better first TD SYNNEX integration for Bifrost than
StreamOne ION when the use case is distributor procurement and fulfillment
visibility.

### Why this is separate from StreamOne ION

The two API families solve different problems:

- `TD SYNNEX Partner API`
  - reseller order / shipment / invoice lookup
  - keyed by known order or invoice identifiers
  - clean `client_credentials` auth
  - good fit for procurement reconciliation and service-desk lookups

- `TD SYNNEX StreamOne ION`
  - cloud commerce / customer / order management
  - broader customer and order surfaces
  - awkward rotating refresh-token auth for current Bifrost runtime
  - better fit for future cloud-order integrations

They should remain separate Bifrost integrations.

### Current scaffold choice

The repo now scaffolds `TD SYNNEX Partner API` as a global integration with
lookup tools rather than an org-mapped sync integration.

That is intentional:

- the available endpoints are keyed by `orderNo` or `invoiceNo`
- I do not see public list/search endpoints in this spec for broad order discovery
- so the best current fit is:
  - global credentials
  - tools that take known identifiers
  - workflows driven by external order numbers from Autotask, HaloPSA, or other procurement systems

### Sources

- Local spec: `/home/thomas/agents/landing/synnex-openapi.json`
- StreamOne note: `/home/thomas/mtg-bifrost/bifrost/docs/plans/2026-03-27-tdsynnex-streamone-readiness.md`
