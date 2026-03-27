# Fork Integration Tests

These tests cover repo-root integration scaffolds under `features/`, `modules/`,
and `workflows/`.

They intentionally live outside `api/tests/` so the fork stays aligned with
upstream CI and test-runner expectations. Upstream's containerized API test
harness mounts the API package and API test tree, not the full repo-root
integration workspace.

Run them locally from the repo root with the project virtualenv:

```bash
./.venv/bin/python -m pytest tests/integrations -q
```
