# Bifrost CI Debugging Playbook

## 1. Inspect Workflow Entry Point

Read:

- `.github/workflows/ci.yml`
- `test.sh`
- `docker-compose.test.yml`

Typical backend CI path:

```bash
./test.sh --coverage --ci
```

## 2. Get the Real Logs

When a GitHub token is available:

```bash
curl -L -H "Authorization: Bearer $GH_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/<owner>/<repo>/actions/jobs/<job-id>/logs
```

Use the log, not just the check annotation.

## 3. Reproduce Narrowly

Preferred:

- `./test.sh tests/unit/...`
- `./test.sh tests/e2e/...`

If Docker is unavailable:

- compile/import sanity
- inspect test files and harness mounts
- call out that full reproduction was not possible

## 4. Inspect the Harness

Check:

- `docker-compose.test.yml` mounts
- `PYTHONPATH`
- `working_dir`
- files visible in `/app`

CI-only failures often come from repo-root assets that are available locally but not mounted into the test runner.

## 5. Fix the Correct Layer

- wrong assertion: fix the test
- missing mount/import path: fix the harness or make dependency explicit
- actual behavior regression: fix code
- deprecation warning: record separately unless it breaks the run
