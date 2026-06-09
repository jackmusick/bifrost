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
