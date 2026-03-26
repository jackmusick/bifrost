# Order Lifecycle Vendor API Research

**Date:** 2026-03-25

## Purpose

Capture the current state of publicly documented API options for order
lifecycle visibility and notifications across vendors that may matter to
Bifrost workflows:

- Dell
- Amazon
- TD SYNNEX
- LuxSci status follow-up

This note is intended to guide prioritization, not to lock implementation.
Vendor onboarding requirements and public docs may change.

## Summary

### Amazon

**Assessment:** Best current fit for Bifrost.

Amazon Business has a workable event-driven model for procurement workflows:

- `Ordering API` can retrieve canonical order state
- package tracking supports push notifications to a webhook
- tracking events include shipment movement, out-for-delivery, delivered, and
  estimated-delivery-date changes

This makes Amazon the clearest candidate for:

- order confirmations
- shipment notices
- delivery updates
- downstream delivery notifications

Recommended architecture:

1. Receive Amazon Business push notifications at a Bifrost-managed endpoint.
2. Deduplicate and validate notifications.
3. Pull canonical order or package state using the relevant Amazon Business API.
4. Emit normalized internal events for downstream workflow handling.

Important constraint:

- package tracking push notifications apply to Amazon Business orders placed
  from external systems such as Ordering API and Punchout, not orders placed
  directly on the Amazon Business website

## Dell

**Assessment:** Workable, but partner-onboarding-heavy.

Dell appears to have a viable order-lifecycle integration surface through its
Premier / TechDirect API ecosystem:

- Purchase Order Acknowledgement Push API
- Order Status Push API
- Order Status Pull API

This suggests Dell can cover:

- purchase-order acknowledgements / confirmation-like events
- order status progression
- shipment tracking information
- delivery-state changes

Dell is less attractive than Amazon operationally because:

- enablement is not self-serve
- the integration requires Dell account-team / integration-team involvement
- webhook security and account-program setup need vendor coordination

Working assumption:

- Dell is a good second-wave target if order visibility from Premier matters
- do not schedule implementation work until Dell onboarding and account
  entitlement are confirmed

## TD SYNNEX

**Assessment:** Partially workable; split between cloud orders and physical
distribution workflows.

The public API surface I could verify is `StreamOne ION`, which is appropriate
for cloud / subscription-style orders:

- list orders
- get order details
- observe status progression
- cancel orders in eligible states

That supports Bifrost use cases around:

- order confirmation / reconciliation
- status polling
- cancellation workflows

What I could **not** verify from public docs:

- a public physical-order shipment-tracking API
- public webhook/event docs for parcel shipping notifications
- a documented delivery-update API for hardware distribution orders

The public TD SYNNEX web properties still point strongly toward portal/report
workflows such as ECExpress and XpressTrak-style reporting rather than a clean
public shipping-event API.

Working assumption:

- `StreamOne ION` is viable if we care about cloud marketplace / subscription
  orders
- physical-order tracking and ship notices should be treated as **unverified**
  until a rep or partner portal exposes a formal API contract

## LuxSci

**Assessment:** Deferred.

LuxSci remains a wildcard. Before spending engineering time here, confirm
whether any customers actually depend on it.

Recommended next step:

- ask internally whether LuxSci is present in any active customer environment
- only do further API research if there is confirmed business relevance

## Prioritization

Recommended order:

1. Amazon
2. Dell, once partner enablement is confirmed
3. TD SYNNEX StreamOne only if cloud-order visibility matters soon
4. TD SYNNEX physical-order tracking only after private API availability is
   confirmed
5. LuxSci only if internal customer usage is confirmed

## Sources

Amazon Business:

- https://developer-docs.amazon.com/amazon-business/docs/retrieving-order-status
- https://developer-docs.amazon.com/amazon-business/docs/retrieving-package-tracking-details
- https://developer-docs.amazon.com/amazon-business/docs/package-tracking-push-notifications

Dell:

- https://developer.dell.com/api/export-pdf/3543296/version/1.0.0?uuid=8cf17d7a-74d7-4312-8794-620f5bed3546
- https://developer.dell.com/api/export-pdf/6026366/version/4.0.0?uuid=11538
- https://developer.dell.com/api/export-pdf/6091136/version/4.0.0?uuid=bea0b0d7-239f-4ee7-b3ff-6ffe6c35ccc4

TD SYNNEX:

- https://docs.streamone.cloud/
- https://www.tdsynnex.com/na/us/smbconnect/resources/ecexpress/
- https://www.tdsynnex.com/na/ca/ecexpress-instructions/
