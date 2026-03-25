# Keeper MSP Integration Design Note

**Date:** 2026-03-25

## Purpose

Document the intended architecture and security boundary for the `Keeper MSP`
integration in Bifrost so it is not mistaken for a general-purpose secrets
backend.

## Decision

Bifrost integrates with Keeper by talking to **Keeper Commander Service Mode**
over HTTP. This exists to manage and query **Keeper itself**, especially the
MSP managed-company surface exposed by `msp-info`.

This integration is **not** the recommended place to store or serve Bifrost's
runtime secrets.

## Why

Keeper Commander is acceptable as a vendor-specific control plane because:

- Keeper's MSP automation surface is centered on Commander / Commander SDK.
- The service mode gives Bifrost a clean HTTP contract instead of automating an
  interactive CLI session directly.
- The useful entity model for Bifrost is Keeper managed companies, not generic
  secret retrieval.

Keeper Commander is a poor primary secrets backend for Bifrost because:

- it introduces a stateful authenticated Keeper session into the automation path
- it adds another privileged service near the cluster
- it is optimized for interacting with Keeper, not for cloud-native workload
  identity and secret delivery
- it broadens the blast radius if the cluster or sidecar is compromised

## Recommended Security Boundary

Use Keeper for:

- managing Keeper MSP tenants and managed companies
- Keeper-specific automation
- human-facing vault workflows where Keeper is already the system being managed

Use an external secrets store such as Azure Key Vault for:

- Bifrost integration credentials
- shared runtime secrets used by workflows
- cluster-consumed secrets that should remain off-cluster at rest

Do not treat Kubernetes `Secret` objects as the source of truth. If Kubernetes
secrets are used at all, they should be treated as a cache or delivery
mechanism for secrets that originate in an external store.

## Preferred Runtime Pattern

1. Run Keeper Commander Service Mode separately, ideally in k3s.
2. Keep Keeper session state and Commander-specific configuration inside that
   service boundary.
3. Point the Bifrost `Keeper MSP` integration at the service with:
   - `base_url`
   - `api_key`
   - optional `api_version`
4. Keep Bifrost's own secrets in Azure Key Vault or another external secret
   manager, accessed via workload identity or tightly scoped service
   credentials.

## Operational Constraints

For the current Bifrost `Keeper MSP` integration to work correctly, the Keeper
Commander service must:

- have an active authenticated Keeper session
- allow the `msp-info` command
- return unencrypted JSON responses to Bifrost

If those conditions are not met, the integration should fail loudly rather than
silently falling back to unsafe or brittle behavior.

## Non-Goals

This design does not attempt to:

- replace Azure Key Vault, HashiCorp Vault, or similar systems
- make Keeper the universal secrets provider for Bifrost
- automate Keeper by shelling out to the interactive CLI from workflow code

## Relevant Implementation

- `modules/keeper.py`
- `features/keepermsp/workflows/data_providers.py`
- `features/keepermsp/workflows/sync_managed_companies.py`
