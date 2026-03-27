# Manifest Transition Guidance

**Date:** 2026-03-27

## Purpose

This note records the current transition rule for this fork while we converge
back toward upstream's repo model.

## Current Rule

- Treat `.bifrost/` as generated or system-managed workspace metadata.
- Do not treat committed `.bifrost/*.yaml` as durable source-of-truth design
  documents.
- Prefer source files under `features/`, `modules/`, `shared/`, `apps/`, and
  platform code under `api/` and `client/` as the authored surface.

## Why

The platform itself already treats `.bifrost/` as generated state in several
places:

- editor writes to `.bifrost/` are blocked as system-generated
- `/api/files/manifest` regenerates manifest files from DB state
- `/api/files/manifest/import` imports manifest files into DB state
- repo sync writers regenerate `.bifrost/*.yaml` into storage

Upstream also does not track a committed `.bifrost/` directory on `main`.

## Transitional Reality In This Fork

This fork still carries committed `.bifrost/*.yaml`, and some local watch or
sync workflows may still depend on those files being present and internally
consistent.

That means:

- reading `.bifrost/*.yaml` for discovery is still acceptable
- small, tactical edits may still be required during local watch/sync work
- those edits should be treated as transitional metadata, not canonical design
  intent

## Operator Guidance

- Do not start new work by hand-authoring `.bifrost/*.yaml` unless the current
  sync path requires it.
- When a manifest change is unavoidable, keep it minimal and expect regeneration
  or import to normalize it later.
- Do not open upstream PRs that include `.bifrost/*.yaml` changes unless
  upstream explicitly asks for them.
- Before doing larger repo-model work, read
  `docs/plans/2026-03-26-upstream-convergence-plan.md`.

## Next Steps

- keep reducing local guidance that describes `.bifrost/*.yaml` as the source
  of truth
- separate fork-only workflow notes from upstreamable code changes
- plan a dedicated migration branch for removing committed `.bifrost/` from the
  fork's normal authored surface
