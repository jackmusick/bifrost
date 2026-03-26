# VIPRE Internal API Assessment

## Summary

VIPRE's browser portal exposes a richer site-management API than the documented
External API, but that internal API is not currently usable with the supported
API-key authentication flow that Bifrost uses.

The practical result is:

- Bifrost should continue using the documented External API for supported
  automation.
- Bifrost should not switch the VIPRE integration to the portal-only
  `/api/v1/{tenantUuid}/esm/site/*` endpoints unless VIPRE provides a supported
  automation auth path for them.
- The current integration should prefer stable `siteUuid` mapping and allow
  friendlier display labels to be curated in Bifrost rather than inferred from
  hostnames alone.

## Evidence

### Public / documented API

The documented VIPRE External API is represented locally in:

- `/home/thomas/agents/integrations/vipre/vipre-endpoint-api.yaml`

That surface includes:

- `GET /ext/site`
- `POST /ext/site`
- `GET /ext/devices`

The spec defines `siteUuid` and `siteName` on device-shaped payloads, but live
responses in the current MSP tenant returned `siteUuid` while leaving
`siteName` null for sampled devices.

### HAR findings

The browser HAR captured from the VIPRE portal is:

- `/home/thomas/agents/landing/midtowntg.myvipre.com.har`

That HAR shows the web UI calling internal endpoints not present in the public
External API contract, including:

- `GET /api/v1/{tenantUuid}/esm/site/listing`
- `GET /api/v1/{tenantUuid}/esm/site/{siteUuid}`
- `GET /api/v1/{tenantUuid}/esm/site/{siteUuid}/details`
- `GET /api/v1/{tenantUuid}/esm/site/attention-counts`
- `GET /api/v1/{tenantUuid}/esm/site/trials-remaining`

Those responses include the fields the public integration was missing:

- `siteUuid`
- short site slug `name`
- human-readable `companyName`
- seat/device counts and other site metadata

Example fields observed in the HAR listing response:

- `siteUuid: "bb2041d8-96bd-4578-9938-a284e02ed7cc"`
- `name: "advancedfamily"`
- `companyName: "Advanced Family Dentistry of Muncie"`

## Auth behavior

Direct probing showed a split between supported API-key auth and portal/session
auth:

- `GET /api/v1/register/site/{slug}/details` works with
  `X-Vipre-Endpoint-Key-Id` and `X-Vipre-Endpoint-Api-Key`
- `GET /api/v1/{tenantUuid}/esm/site/*` returned `401 Unauthorized` with the
  same API-key auth

That means the richer site-listing surface is not currently automation-safe for
the Bifrost integration using the documented VIPRE credentials.

The HAR suggests browser-session-backed access, but it does not conclusively
prove OAuth. A login-flow capture would be required to determine whether the
portal is backed by OAuth/OIDC, SAML, or another session model.

## Integration impact

The current Bifrost VIPRE integration in:

- `/home/thomas/mtg-bifrost/bifrost/modules/vipre.py`

still needs to infer child sites from supported External API data. Because the
live API omitted `siteName`, the fallback to the `backtrack-details` hostname
slug remains justified for discovery.

However, hostnames such as `advancedfamily.myvipre.com` are not a good final
display label for users. They are acceptable as discovery hints, but not as the
best long-term user-facing name.

## Recommendation

1. Keep the integration on the documented External API for now.
2. Do not adopt the portal `/esm/site/*` endpoints as a primary integration
   dependency without a supported non-browser auth path from VIPRE.
3. Improve Bifrost's VIPRE UX by allowing mapped entities to display a curated
   friendly label, using the real customer name when known.
4. If VIPRE support can provide a supported site-list endpoint or approved auth
   method for the portal API, revisit the integration and replace hostname-based
   inference with direct site listing.

## Follow-up work

- Track a Bifrost UX issue to let VIPRE mappings surface a friendly display
  name instead of only the hostname slug.
- If VIPRE responds with supported access to the richer site endpoints, validate
  that auth path and update the integration accordingly.
