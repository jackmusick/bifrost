# Bifrost Integration Checklist

- Does `modules/{vendor}.py` encapsulate vendor-specific API behavior cleanly?
- Are auth and config reads centralized?
- Do data providers return sorted `{value, label}` options?
- Does the sync workflow handle match-or-create logic explicitly?
- Are mapping upserts non-destructive and idempotent?
- Are `.bifrost/` edits limited to what the current fork workflow still requires?
- Are tests covering config contract, normalization, and sync behavior?
- Did you avoid moving a unit test to E2E just because of brittle local path assumptions?
