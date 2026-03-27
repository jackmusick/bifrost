# Dell Procurement Integration Readiness

## Summary

Dell looks viable for Bifrost, but not as a self-serve API integration.

The path is a Premier / procurement integration project that requires:

- Dell sales / online team engagement
- partner-account enablement
- a secured webhook receiver for push APIs
- internal business ownership for order-lifecycle automation

The right Bifrost model is not "just add credentials and poll an endpoint."
It is a procurement integration with both onboarding and platform work.

## What Dell Public Material Confirms

Dell's public `Dell Premier APIs` deck confirms the API family relevant to
Midtown's order-lifecycle use case:

- Purchase Order API
- Order Status API
- Purchase Order Acknowledgements (POA) API
- Advanced Ship Notifications (ASN) API
- Invoice API

The deck says:

- Order Status supports both pull and push
- POA is push
- ASN is push
- payloads support JSON and XML
- Order Status/ASN include tracking and revised delivery information

The public deck also states the starting motion explicitly:

- "Contact your Dell Technologies Sales Representative"
- customer needs business/IT resources and technical API capability
- timeline ranges from weeks to months

## Public Source Limits

The broader Premier API deck remains public, but the more granular individual
developer portal PDF exports that were previously reachable now return `401`.

That means we can still justify the integration direction publicly, but exact
endpoint contracts and security details likely need Dell-side access or account
onboarding.

## What Midtown Needs To Have In Hand

Before a real Bifrost integration is worth building, Midtown needs:

1. A Dell program path

- Confirm whether Midtown is onboarding through Premier, TechDirect, or another
  Dell procurement program surface.
- Identify the Dell sales / online team contact who owns API enablement.

2. API enablement from Dell

- Enable the relevant Premier procurement APIs:
  - Purchase Order API
  - Order Status API
  - POA API
  - ASN API
  - Invoice API if reconciliation matters
- Obtain the official implementation docs and schema/contracts for the enabled
  APIs.

3. Security / connectivity decisions

- Decide whether Midtown will consume:
  - pull only
  - push only
  - or push + pull reconciliation
- If using push, provide Dell with a secured webhook endpoint.
- Confirm supported auth mode for Dell push callbacks in Midtown's program:
  - OAuth2
  - API key
  - Basic auth

4. Business identifiers and data mapping

- Decide which internal keys Bifrost should anchor on:
  - PO number
  - requisition number
  - Dell order number
  - line item identifiers
- Decide where Dell orders will land in Bifrost:
  - order table
  - notifications/events
  - procurement app
  - Autotask ticket/project linkage

5. Operational ownership

- Procurement/contact owner for Dell onboarding
- Technical owner for webhook operation and support
- Internal user who will validate event accuracy against real orders

## Recommended Bifrost Architecture

### Phase 1: Event ingestion first

Use Dell push APIs as the primary real-time signal:

- POA for accept/reject and line mapping
- ASN for shipment and tracking events
- Order Status Push for revised dates and lifecycle changes

Bifrost responsibilities:

- authenticated webhook endpoint
- payload persistence
- deduplication / replay handling
- normalized event model
- routing into UI / alerts / downstream workflows

### Phase 2: Pull reconciliation

Add Order Status Pull as a recovery and reconciliation path:

- rehydrate missed events
- verify final delivery state
- backfill after downtime

This is especially important if webhook delivery guarantees are weak or Dell's
push payloads are sparse.

### Phase 3: Downstream workflow integration

After ingestion is reliable:

- create procurement/order dashboards
- generate shipment/delay notifications
- reconcile invoices if Dell Invoice API is enabled
- optionally link orders to Autotask or internal purchasing workflows

## Success Criteria For A First Real Integration

Midtown should consider Dell "ready" when all of the following are true:

- Dell confirms Midtown is API-enabled for the relevant Premier procurement APIs
- Midtown has official Dell docs/contracts for the enabled APIs
- Midtown has credentials and/or webhook security material
- Midtown has a reachable webhook endpoint design
- Midtown has identified the internal order identifiers to track

Without those, a Bifrost "Dell integration" would only be speculative scaffolding.

## Suggested Next Midtown Steps

1. Ask the Dell rep / online team which exact Premier APIs can be enabled for Midtown.
2. Request the official docs for:
   - Order Status Push
   - Order Status Pull
   - POA
   - ASN
3. Confirm supported webhook auth methods and any IP allowlist expectations.
4. Decide whether Midtown wants shipment/delivery events only, or full PO to invoice visibility.
5. Once docs and enablement are in hand, implement Dell in Bifrost as:
   - a webhook-capable procurement integration
   - with pull reconciliation, not just a simple REST poller

## Sources

- `https://www.delltechnologies.com/asset/en-us/solutions/premier-solutions/briefs-summaries/dell-premier-api-introduction-direct.pdf`
- local research note in `/home/thomas/agents/integrations/dell`
