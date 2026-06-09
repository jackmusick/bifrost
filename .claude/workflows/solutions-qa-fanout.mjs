export const meta = {
  name: 'solutions-qa-fanout',
  description: 'Adversarial UI/CLI QA on Solutions: 6 axis agents (own worktree + port-mode stack) drive real UI/CLI, findings independently verified, then synthesized into a ranked backlog',
  phases: [
    { title: 'Cleanup', detail: 'kill stray stacks, prune merged worktree-agent-* branches' },
    { title: 'Find', detail: 'one agent per axis; each provisions its own port-mode debug stack and drives UI+CLI' },
    { title: 'Verify', detail: 'independent agent refutes/confirms each reproduced finding' },
    { title: 'Synthesize', detail: 'dedup, rank, write the findings backlog' },
  ],
}

// One finding produced by an axis agent.
const FINDING_SCHEMA = {
  type: 'object',
  properties: {
    axis: { type: 'string' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          title: { type: 'string' },
          surface: { type: 'string', enum: ['forms-ui', 'apps-ui', 'solutions-page', 'cli', 'mcp', 'export-import', 'other'] },
          severity: { type: 'string', enum: ['critical', 'high', 'medium', 'low', 'info'] },
          did: { type: 'string', description: 'Exact steps/commands/URLs to reproduce' },
          observed: { type: 'string', description: 'What actually happened (note screenshot path for UI)' },
          expected: { type: 'string' },
          reproduced: { type: 'boolean', description: 'true only if actually run and observed' },
          code_ref: { type: 'string', description: 'file:line best guess at cause, if known' },
        },
        required: ['title', 'surface', 'severity', 'did', 'observed', 'expected', 'reproduced'],
      },
    },
    coverage_note: { type: 'string', description: 'What within the axis was tested and what was NOT reached' },
    blocked: { type: 'boolean', description: 'true if the agent could not boot a healthy stack' },
  },
  required: ['axis', 'findings', 'coverage_note'],
}

// One verifier verdict on a single finding.
const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    title: { type: 'string' },
    confirmed: { type: 'boolean', description: 'true only if the verifier reproduced it' },
    note: { type: 'string', description: 'what the verifier observed when re-running the repro' },
  },
  required: ['title', 'confirmed', 'note'],
}

// Injected into every axis agent. Each agent provisions its OWN isolated,
// port-mode debug stack (Chrome/Playwright cannot drive netbird stacks), drives
// it, and tears it down. Per-worktree Compose project name = automatic isolation.
const REPO = '/home/jack/GitHub/bifrost'
const BASE_WORKTREE = `${REPO}/.claude/worktrees/solutions-success-criteria`

const BOOTSTRAP = `
YOU PROVISION YOUR OWN STACK. Do this before any testing, and tear it down at the end.

1. Create an isolated worktree off the branch under test:
   AXIS=<your-axis-key>
   WT=/tmp/qa-$AXIS
   git -C ${BASE_WORKTREE} worktree add "$WT" HEAD
   cd "$WT"

2. Boot a PORT-MODE stack (MANDATORY — netbird stacks can't be driven by a browser):
   env -u NETBIRD_SETUP_KEY ./debug.sh up
   ./debug.sh status        # capture the http://localhost:<port> URL — call it $URL
   If the api container is not healthy within ~90s, retry \`env -u NETBIRD_SETUP_KEY ./debug.sh down && env -u NETBIRD_SETUP_KEY ./debug.sh up\` ONCE. If still unhealthy, set blocked=true in your output and STOP (do not invent findings).

3. Install the API-matched CLI in a scratch dir OUTSIDE the repo:
   mkdir -p /tmp/qa-cli-$AXIS && cd /tmp/qa-cli-$AXIS
   python3 -m venv .venv && .venv/bin/pip install --quiet --upgrade pip
   .venv/bin/pip install --quiet "$URL/api/cli/download"
   .venv/bin/bifrost login --url "$URL" --email dev@gobifrost.com --password password
   Run the CLI FROM /tmp/qa-cli-$AXIS (its .env carries the tokens). Default creds: dev@gobifrost.com / password (superuser, MFA off).

4. Drive the UI with Playwright against $URL (headless is fine). Capture screenshots
   to /tmp/qa-$AXIS/shots/ for any UI finding and put the path in observed.

5. TEARDOWN (always, even on failure): cd "$WT" && env -u NETBIRD_SETUP_KEY ./debug.sh down ; git -C ${BASE_WORKTREE} worktree remove --force "$WT"

RULES OF ENGAGEMENT:
- VERIFY EMPIRICALLY. Reading code forms hypotheses; driving the running stack concludes. A finding is REAL only if you reproduced it on your stack — include exact commands/URLs/clicks and observed-vs-expected.
- You MAY create solutions/workflows/tables/configs/forms/apps and install them to orgs to set up tests. Correctness findings matter more than tidiness.
- Do NOT modify product source. This is a drive/audit pass. Throwaway fixtures via CLI/API/UI are fine.
- If you could not boot a healthy stack, return blocked=true with an empty findings array — never fabricate.
`
