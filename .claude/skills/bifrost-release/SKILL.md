---
name: bifrost:release
description: Build and release Bifrost. Use when pushing commits to main, cutting a versioned release, or deploying to K8s. Handles dev push (CI builds :dev image) and full release (version tag → GitHub Release + :latest).
---

# Bifrost Release

## Step 1: Ask which workflow

> "Are you doing a **dev push** (push commits → CI builds `:dev`) or a **full release** (version tag → GitHub Release + `:latest`)?"

---

## Dev Push

For rapid iteration — commits on main, CI handles the build.

### 1. Check state

```bash
git status --short
git log --oneline origin/main..HEAD
```

Report: any uncommitted changes, how many commits ahead of origin.

### 2. Run local unit tests (sanity check)

```bash
./test.sh tests/unit/
```

**If tests fail:** show the failures and stop. Do not push until they pass.

### 3. Summarize commits since last release

```bash
git describe --tags --abbrev=0 2>/dev/null || echo "no-prior-tag"
```

Then run:
```bash
LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null)
git log ${LAST_TAG}..HEAD --oneline 2>/dev/null || git log --oneline origin/main..HEAD
```

Present the summary as:

> **Commits since `<last-tag>`:**
>
> ⚠️ **Breaking changes:** *(list any commits whose message contains `BREAKING`, `breaking change`, or uses the `!:` conventional-commit marker — e.g., `feat!:`, `fix!:`. If none, omit this section.)*
>
> **All commits:**
> - `<sha>` `<message>`
> - ...

### 4. Push

```bash
git push origin main
```

### 5. Tell the user what happens next

> "Pushed. CI will now:
> 1. Run **unit tests** (fast ~2 min) — if they pass:
> 2. Build and push `ghcr.io/jackmusick/bifrost-api:dev` and `ghcr.io/jackmusick/bifrost-client:dev`
> 3. Also tag `ghcr.io/jackmusick/bifrost-api:<git-describe>` for traceability
>
> E2E tests run in parallel but don't block the build.
>
> K8s pods on `:dev` will pick up the new image on next restart/rollout. To force a rollout:
> ```bash
> kubectl rollout restart deployment/bifrost-api deployment/bifrost-worker deployment/bifrost-scheduler deployment/bifrost-client -n bifrost
> ```
>
> Watch CI: https://github.com/jackmusick/bifrost/actions"

---

## Full Release

For a named version — creates a GitHub Release, tags `:latest`, and sets the baseline for future `git describe` dev versions.

### 1. Determine version

Ask: "What version? (current git describe: run `git describe --tags --always`)"

The tag must start with `v` — e.g., `v2.1.0`.

### 2. Summarize commits since last release

```bash
LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null)
git log ${LAST_TAG}..HEAD --oneline
```

Present the summary as:

> **Commits since `<last-tag>`:**
>
> ⚠️ **Breaking changes:** *(list any commits whose message contains `BREAKING`, `breaking change`, or uses the `!:` conventional-commit marker — e.g., `feat!:`, `fix!:`. If none, omit this section.)*
>
> **All commits:**
> - `<sha>` `<message>`
> - ...

Show this to the user and confirm they want to proceed with tagging.

### 2b. Credit external contributors

Find PRs merged since the last release that were authored by someone other than the repo owner — they must be credited in the release notes.

```bash
LAST_TAG_DATE=$(git log -1 --format=%cI $(git describe --tags --abbrev=0))
gh pr list --state merged --base main --search "merged:>=${LAST_TAG_DATE}" \
    --limit 200 --json number,title,author,mergedAt \
    | jq -r '.[] | select(.author.login != "jackmusick") | "#\(.number) @\(.author.login) — \(.title)"'
```

Include a **Contributors** section in the release notes listing each PR with author attribution (e.g., `- #22 by @sdc53 — embed token sessionStorage fix`). If a PR's change maps to a bullet you've already written elsewhere in the notes, append the `(#NN by @user)` credit to that bullet too.

### 3. Run pre-tag checks

```bash
./scripts/release-check.sh <tag>
```

This verifies:
- Working tree is clean
- Tag doesn't exist locally or on remote
- You're on `main`
- Unit tests pass

**If it fails:** show the failures and stop. Do not proceed.

### 4. Tag and push

```bash
git tag <tag>
git push origin <tag>
```

### 5. Tell the user what happens next

> "Tag `<tag>` pushed. CI will now:
> 1. Run **unit tests + E2E tests** (both required for a release, ~12 min total)
> 2. Build and push images:
>    - `ghcr.io/jackmusick/bifrost-api:<version>` (e.g., `2.1.0`)
>    - `ghcr.io/jackmusick/bifrost-api:2.1` and `ghcr.io/jackmusick/bifrost-api:2`
>    - `ghcr.io/jackmusick/bifrost-api:latest`
>    - Same for `bifrost-client`
> 3. Create a GitHub Release at https://github.com/jackmusick/bifrost/releases
>
> After CI completes, K8s pods on `:latest` or `:<version>` will need a rollout:
> ```bash
> kubectl rollout restart deployment/bifrost-api deployment/bifrost-worker deployment/bifrost-scheduler deployment/bifrost-client -n bifrost
> ```
>
> CLI users on `:latest` will automatically get the new version next `pipx install`.
>
> Watch CI: https://github.com/jackmusick/bifrost/actions"

---

## K8s Quick Reference

**Current image tags in use** (all in namespace `bifrost`):
- `api`, `init container`, `worker`, `scheduler` → `ghcr.io/jackmusick/bifrost-api:dev`
- `client` → `ghcr.io/jackmusick/bifrost-client:dev`

**Force rollout after a push:**
```bash
kubectl rollout restart deployment/bifrost-api deployment/bifrost-worker deployment/bifrost-scheduler deployment/bifrost-client -n bifrost
```

**Check what version is running:**
```bash
curl -s https://bifrostdev.musick.gg/api/version | python3 -m json.tool
```

**Pin to a specific release (e.g., v2.1.0):**
Update `kubernetes/components/bifrost/*/deployment.yaml` image tags from `:dev` to `:2.1.0`, commit, and apply.
