# Chat UX Overhaul — Design Spec

**Sub-project:** (1) of the Chat V2 program
**Status:** Design draft
**Author:** Jack Musick + Claude
**Date:** 2026-04-27
**Program spec:** `2026-04-27-chat-v2-program-design.md`
**Master plan:** `../plans/2026-04-27-chat-v2-master-plan.md`

## Goal

Bring the Bifrost chat experience to feature parity with Claude.ai for everyday use. Add the foundational UX primitives — workspaces, attachments, lossless compaction, model curation — that the rest of the Chat V2 program (Code Execution, Skills, Artifacts, Web Search) will build on.

## Non-goals

- Branching/tree conversations (linear-only).
- Voice input/output.
- Conversation-level full-text search (sidebar filter only in v1).
- Auto-routing between models (user picks; admin curates).
- Real-time collaboration (multiple users in one chat).
- Skills, Artifacts, Code Execution surfaces — those are later sub-projects, but this spec leaves the seams.

## Scope summary

| Feature | Shape | Section |
|---|---|---|
| Edit user message + retry | Edit replaces, retry regenerates, no branch history | §1 |
| Workspaces | First-class folders + scoped configuration | §2 |
| Tool layering | Workspace ∩ Agent (intersection) | §2.4 |
| Attachments | Files only — images, PDFs, CSVs, text, screenshots | §3 |
| Lossless compaction | Auto at threshold + manual button; DB unchanged | §4 |
| Context budget indicator | Per-model-aware tokens + symbolic cost tier badges | §4.2, §5.5 |
| Model resolver | Shared infrastructure; allowlist chain with provenance | §5 |
| Per-message regenerate | With optional model override | §1.2 |
| Per-conversation instruction override | Hidden behind settings; not a primary affordance | §6 |
| Multi-agent within turn | Within-turn delegation via existing `delegated_agent_ids` | §7 |
| Conversation rename/delete/export | Inline rename, soft-delete, markdown/JSON export | §8 |
| Sidebar search | Title + last-message-preview filter only | §9 |

## 1. Edit user message + retry

### 1.1 Edit user message
Replaces the message in place; conversation continues from the edited message. **No branching** — the previous version of the message is not retained in DB. The assistant's prior reply (and any messages after the edited message) are discarded when the user submits the edit.

UI: pencil icon on user messages on hover. Click → message becomes editable inline. Submit re-runs from this point. Cancel reverts.

Implementation note: the existing `Message.sequence` field stays linear. Edit = `DELETE FROM messages WHERE conversation_id = ? AND sequence > ?`, then update the edited message, then run a new turn.

### 1.2 Retry last response
Regenerates the most recent assistant message. The previous assistant message is replaced (not kept).

UI: refresh icon on the assistant message. Default click → retry with current conversation model. Adjacent dropdown → "Retry with [other model]" — picks from the user's allowed model set (§5). Switching models via retry sets the conversation's current model going forward.

## 2. Workspaces

### 2.1 What a workspace is
A workspace is a folder for conversations plus optional shared configuration. **Every conversation belongs to exactly one workspace.** A synthetic "Personal" workspace is auto-created per user as the default for unfiled chats.

### 2.2 Workspace fields
| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | UUID | yes | |
| `name` | str | yes | |
| `description` | str | no | |
| `scope` | enum: `personal` / `org` / `role` | yes | |
| `role_id` | UUID | yes if scope=role | |
| `org_id` | UUID | yes if scope=org/role | |
| `user_id` | UUID | yes if scope=personal | |
| `default_agent_id` | UUID | no | Workspace's default agent for new chats |
| `enabled_tool_ids` | list[UUID] | no | If set, tools available in this workspace are intersected with agent's tools (see §2.4) |
| `enabled_knowledge_source_ids` | list[UUID] | no | Knowledge sources added to model context for chats in this workspace |
| `instructions` | text | no | Free-text appended to system prompt for chats in this workspace |
| `default_model` | str | no | See §5 |
| `allowed_models` | list[str] | no | See §5 |
| `created_by` | UUID | yes | |
| `created_at` / `updated_at` | datetime | yes | |
| `is_active` | bool | yes | Soft-delete |

### 2.3 Scope semantics
- **personal**: visible only to `user_id`. The synthetic "Personal" workspace per user.
- **org**: visible to anyone in `org_id`, subject to role gating.
- **role**: visible to members of `role_id`.

Mirrors the existing scoping model used by forms, agents, workflows, tools.

### 2.4 Tool intersection rule
When a chat runs in a workspace, the **effective tool set** for an agent is `agent.tool_ids ∩ workspace.enabled_tool_ids` (if `enabled_tool_ids` is set; otherwise just `agent.tool_ids`). Workspaces can restrict but **never expand** an agent's tool set. This gives admins predictable safety guarantees: if a workspace says "no code execution," that's true regardless of which agent the user picks.

### 2.5 Workspace UI
- Sidebar shows workspaces as collapsible folders, each containing its conversations.
- "+ New workspace" button creates a workspace (modal: name, scope, optional fields).
- Workspace settings page (gear icon) for editing fields.
- Conversations can be moved between workspaces the user has access to (drag, or right-click → Move).
- The synthetic "Personal" workspace cannot be deleted or have its scope changed.

### 2.6 Conversation default workspace
When the user starts a new chat without picking a workspace, it goes into their Personal workspace. The chat URL (`/chat/:conversationId`) is unaffected — workspace is metadata on the conversation, not part of the URL structure.

## 3. Attachments

### 3.1 Supported types
- **Images**: PNG, JPEG, WebP, GIF — sent as vision content blocks if the model supports them.
- **PDFs**: text-extracted server-side; first page rendered as preview thumbnail.
- **CSVs**: parsed; first ~20 rows shown as preview; full contents available to the model as text.
- **Text files**: `.txt`, `.md`, `.json`, `.yaml`, code files. Inline.

### 3.2 Upload flow
- Drag-and-drop into the chat input area, or paperclip button.
- Reuses existing `client/src/stores/uploadStore.ts` plumbing.
- Files upload to S3 under `_attachments/{conversation_id}/{uuid}_{filename}`.
- Per-attachment limits: 25 MB per file, 5 files per message. Total per conversation: configurable per org, default 500 MB.

### 3.3 Wire format
New `ChatStreamChunk` types are not needed for attachments themselves — they're part of the user message at send time, not a streaming chunk. The Message ORM gets a new `attachments` relationship to a new `MessageAttachment` table:

| Field | Type |
|---|---|
| `id` | UUID |
| `message_id` | UUID FK |
| `s3_key` | str |
| `filename` | str |
| `content_type` | str |
| `size_bytes` | int |
| `extracted_text` | text (nullable; for PDFs and the like) |
| `created_at` | datetime |

### 3.4 What attachments aren't
Bifrost-internal entities (tickets, workflow runs, form submissions, table rows) are **not** attachments. Those reach the agent through knowledge sources or tools, not through the attachment system. This keeps the attachment plumbing simple and reserves "attachment" for "the user picked a file from outside Bifrost."

## 4. Compaction & context management

### 4.1 Lossless compaction
Today, when a conversation exceeds 120k tokens, old messages are *deleted* from the model's context. For Chat V2:

- The **database is the source of truth and is never modified by compaction.** All original messages remain visible in the conversation scrollback.
- When the working context exceeds the threshold (some fraction — say 85% — of the current model's context window), the older messages are **summarized into a `[Conversation history summary]` block** which replaces them in the *model's working context only*.
- The summary is generated by a small auxiliary call to a cheap model (the summarizer call uses the model resolver to pick — typically the org's "fast" tier model).
- Result: the model sees a coherent summary plus recent turns; the user still sees their full conversation.

### 4.2 Per-model-aware threshold
The 120k constant becomes per-model. The model resolver (§5) exposes the model's `context_window_tokens` field; the auto-compaction threshold is `0.85 * context_window_tokens`. Switching to a smaller model mid-conversation can immediately put the working context over budget — in that case, compaction runs at the next turn (or earlier if explicitly invoked).

### 4.3 Manual compaction button
"Compact older turns" button in the chat header. Visible always; suggested visually when the budget indicator approaches 70%. Click → runs the same summarization the auto path would, immediately. User feedback: "Compacted N earlier turns into a summary."

### 4.4 Tool output protection
The existing `TOOL_OUTPUT_PROTECT_TOKENS=10000` heuristic carries over: recent tool outputs are kept verbatim during compaction (within a budget). Older tool outputs get summarized along with the surrounding messages.

### 4.5 What compaction sees
A compacted block in working context looks like:

```
[Conversation history summary, covering turns 1-12 (~28k tokens originally):
- User asked about onboarding flow for new MSP clients...
- Assistant explained step-by-step process and provided a checklist...
- Tool calls: created_ticket, sent_email...
- ...]
```

Recent N turns (where N is determined by remaining budget) are kept verbatim.

## 5. Model resolver — shared infrastructure

### 5.1 Why shared
Today, model selection happens ad-hoc in chat (`agent_executor.py`), in workflows (model passed via SDK), in summarization (hardcoded). Chat V2 introduces multi-level model curation. Doing this once, correctly, in a shared utility avoids drift and makes future sub-projects (Skills, Artifacts) inherit the right behavior for free.

### 5.2 Resolver location
`api/shared/model_resolver.py` — exports `resolve_model(context: ModelResolutionContext) -> ModelChoice`.

### 5.3 The chain
Most-specific wins:

```
Platform allowlist  (Bifrost ships supporting these)
        ↓ intersect
Org allowlist       (admin's chosen subset)
        ↓ intersect
Role allowlist      (optional)
        ↓ intersect
Workspace allowlist (optional)
        ↓ intersect
Conversation override (optional, set when user picks via picker)
        ↓ intersect (effectively a single choice at this point)
Message override    (optional, used by retry-with-different-model)
```

At each level, two fields:
- `allowed_models: list[str] | None` — narrows the set
- `default_model: str | None` — picks from the current allowed set

Resolution: walk top-down, intersect allowlists, then walk bottom-up to find the most specific `default_model` that's still in the allowed set. If no level specifies a default, use the org default; if no org default, the platform default.

### 5.4 Used by
v1: chat (this sub-project), summarization-on-compaction (this sub-project's compaction logic).
Future: workflows, skills, artifacts, web search — they all gain it for free by calling the same resolver.

### 5.5 UI: provenance for restricted models
The model picker in chat shows the user's full allowed set (after intersection). Models that *would* exist at a higher level but were restricted at a lower level are shown grayed out with a tooltip naming the restricting level:

- "Claude Opus 4.7 — restricted by your org admin"
- "GPT-5o — restricted by this workspace ('Customer Replies' allows only Haiku and Sonnet)"
- "Llama 3.3 — restricted by your role (Help Desk)"
- "Mistral Large — not enabled on this Bifrost installation"

The picker UI is the OpenRouter-style affordance: visible-but-disabled options communicate availability and access controls in the same view.

### 5.6 Cost surfacing — symbolic, not dollars
Each model in the platform registry has a `cost_tier: "fast" | "balanced" | "premium"` field, with glyphs ⚡ / ⚖ / 💎. Admins can override the tier when adding a model to the org allowlist (e.g., "we treat Sonnet as our balanced default, even though Anthropic prices it as premium").

In the chat UI:
- Model picker shows tier glyph next to each model name.
- Per-message footer on the assistant response shows which tier handled it.
- Per-conversation header shows aggregate ("⚡ ⚡ ⚖ ⚖ 💎 across 5 messages").
- **No dollar amounts in the user-facing chat.** Dollars exist in the admin cost dashboard (`AIUsage` is already there); chat is anxiety-free.

### 5.7 Platform model registry
Platform-level model list lives in `api/shared/model_registry.py` — a static (initially) module that lists every model Bifrost knows about, with: provider, model_id, display_name, context_window_tokens, default_cost_tier, capabilities (vision, tool_use, etc.). Org admins pick from this list when configuring their allowlist.

Future: this becomes dynamic (orgs can register custom-hosted models, e.g., self-hosted Llama via vLLM endpoint). v1 is static.

### 5.8 Provider/model migration — guarding against deprecation

Real-world: providers retire models. Customers switch providers. Anthropic deprecates Claude 3.5 Sonnet → Claude Sonnet 4.6 → Claude Sonnet 5. If we store raw provider model IDs in workspaces, orgs, roles, agents, conversations, and workflow code, every deprecation is a multi-table find-and-replace nightmare with no safe automation. Two layers prevent that.

**5.8.1 Logical model aliases (primary handle).**

The model registry includes first-class logical aliases that point at real models:

| Logical alias | Description | Current target |
|---|---|---|
| `bifrost-fast` | Cheap, fast, suitable for short-context tasks | `claude-haiku-4-5` |
| `bifrost-balanced` | General-purpose default | `claude-sonnet-4-6` |
| `bifrost-premium` | Highest quality, most expensive | `claude-opus-4-7` |
| `bifrost-vision-fast` | Cheap model with vision support | `claude-haiku-4-5` |
| (orgs can define their own aliases too, e.g., `acme-default`) | | |

Workspaces, roles, orgs, and agents reference aliases by default in their `default_model` / `allowed_models` fields. The model picker UI shows both ("⚖ Balanced — Claude Sonnet 4.6") so the alias is the *stable handle* and the underlying real model is *visible*. When Anthropic deprecates Sonnet 4.6, an admin (or Bifrost upstream releases) updates `bifrost-balanced`'s target to the new model. **Everything downstream keeps working with no row rewrites.**

Aliases live in the platform registry plus an `org_model_aliases` table for org-defined ones. The resolver follows alias → target as part of the lookup chain.

**5.8.2 Raw model IDs are still valid.**

An org or user who wants to pin to a specific raw model ID (e.g., for compliance reasons — "we're approved to use Sonnet 4.6 specifically") can do that. They then own the migration when that model deprecates.

**5.8.3 Deprecation remap table.**

The platform ships a `model_deprecations` registry — a list of `{old_model_id, new_model_id, deprecated_at}` entries maintained upstream. The resolver applies remaps at *lookup time* (not by rewriting stored data). When `claude-3-5-sonnet-20240620` is deprecated and remapped to `claude-sonnet-4-6`:

- A workspace whose `default_model` is `claude-3-5-sonnet-20240620` resolves to `claude-sonnet-4-6` automatically.
- The picker shows the deprecation explicitly: "Claude 3.5 Sonnet (deprecated → using Claude Sonnet 4.6)" so admins know to update.
- Optional: a background sweep rewrites stored references after a grace period (e.g., 90 days post-deprecation) so the lookup-time indirection doesn't accumulate forever. Configurable per-org.

**Who maintains what:**
- *Platform-wide remaps* are maintained by Bifrost upstream as part of the model registry. New deprecations ship with Bifrost releases. Self-hosters automatically pick up new entries on upgrade.
- *Org-level remaps* (`org_id` set on the row) are managed by org admins via the admin UI. They override platform-wide remaps for that org. Use case: "we don't use Anthropic anymore, redirect every Anthropic model ID to our self-hosted Llama."
- The resolver applies *org-level first*, then *platform-wide*, so an org override wins.

**5.8.4 `Message.model` is immutable history.**

The `model` field on a Message records *what actually handled this turn at the time*. It is **never remapped or migrated**. "This message was handled by `claude-3-5-sonnet-20240620` on 2025-08-15" is an audit fact, not a configuration. The deprecation remap applies only to *configuration* fields:

| Field | Subject to alias resolution? | Subject to deprecation remap? |
|---|---|---|
| `Org.default_chat_model` | yes | yes |
| `Org.allowed_chat_models[]` | yes | yes |
| `Role.default_chat_model` | yes | yes |
| `Role.allowed_chat_models[]` | yes | yes |
| `Workspace.default_model` | yes | yes |
| `Workspace.allowed_models[]` | yes | yes |
| `Conversation.current_model` | yes | yes |
| `Agent.default_model` | yes | yes |
| `Message.model` | NO (historical record) | NO (historical record) |

**5.8.5 Save-time validation in AI settings (the safety net).**

The aliases and deprecation table cover the *expected* migration paths. The save-time validator catches the *unexpected* ones — admin changes that orphan model references without realizing it.

Triggering events:
- Admin removes a model from `Org.allowed_chat_models`.
- Admin switches the AI provider integration (OpenRouter → direct Anthropic, etc.) such that previously-reachable models are no longer reachable.
- Admin disables an integration that was the path to certain models.
- Admin deletes an org-level alias that has downstream references.

When any of these happens at save time, the system runs a **reference audit** that scans every place a model ID can be stored:

| Location | Field |
|---|---|
| Workspace | `default_model`, `allowed_models[]` |
| Role | `default_chat_model`, `allowed_chat_models[]` |
| Org | `default_chat_model`, `allowed_chat_models[]` |
| Conversation | `current_model` |
| Agent | `default_model` |
| Workflow code | grep for hardcoded model IDs (heuristic, surfaced as warnings) |

`Message.model` is **excluded** from the audit — it's immutable history (per §5.8.4).

If references to soon-to-be-orphaned models exist, the admin sees a remediation UI:

> ⚠ Saving these changes will orphan some model references:
> - **`minimax-m1`** is referenced in 3 places (1 workspace, 2 conversations). Choose a replacement: [picker, suggested default = closest available model in same cost tier]
> - **`gpt-4o`** is referenced in 5 places (1 role default, 4 conversations). Choose a replacement: [picker]
>
> [ Cancel ] [ Apply replacements and save ]

On apply, the chosen replacements are written *both* to the affected rows AND to the org-level deprecation remap table so any future references to the old IDs (e.g., from a workflow that hadn't been updated yet) also resolve. This dual-write is intentional — the row rewrite cleans up *known* references, the remap entry catches *unknown* ones (workflow strings, conversation overrides set after the migration started, etc.).

**Suggested replacement heuristic:** for each orphaned model, find the closest available model in the same `cost_tier`. Tie-break by provider preference (an admin setting). The admin can override every suggestion individually before applying.

**API:** `POST /api/admin/models/migrate-references` takes `{replacements: {old_model_id: new_model_id, ...}}` and returns a summary of what was changed where. Idempotent — running twice with the same input is a no-op.

**5.8.6 Display name overrides.**

Independently of provider/migration concerns, an org admin can override the user-facing display name of any model. Useful for white-labeling or for using internal language ("Acme Pro" instead of "Claude Opus 4.7"). The override lives on the org's model entry; the actual provider model ID stays correct because that's what's used to call the API.

| Field | Purpose |
|---|---|
| `org.allowed_chat_models[].model_id` | Real provider ID — used for API calls |
| `org.allowed_chat_models[].display_name_override` | User-facing label, defaults to platform registry's display name |
| `org.allowed_chat_models[].cost_tier_override` | Optional, defaults to platform registry's tier |

This is a thin org-wide UX customization; doesn't intersect with the resolver's model-selection logic at all.

**5.8.7 Why this is better than the alternatives.**

Claude.ai and ChatGPT hide the model entirely. Power users have no idea what they're running. OpenRouter exposes raw IDs with no indirection — every change is a manual update. Vercel AI SDK has `customProvider` aliases but no curation, no per-org views, no save-time validation. Bifrost's aliases-with-visibility model plus the save-time orphan check is a real differentiator and the implementation cost is moderate (the audit logic is mostly SQL queries; the UI is a single modal at admin-save time).

## 6. Per-conversation custom instructions

A conversation gets an optional `instructions: text` field (separate from workspace.instructions). When set, it's appended to the system prompt for that conversation only.

UI: settings menu in conversation header → "Customize this chat" → text area. Not surfaced as a primary affordance; users who don't open the menu won't know it exists. Suitable for "this one chat needs to behave differently from the rest of my Customer Replies workspace."

When set, system prompt assembly is: `agent.system_prompt + workspace.instructions + conversation.instructions`. (Plus knowledge sources, tools schema, etc.)

## 7. Multi-agent within turn

The existing `Agent.delegated_agent_ids` field (declared, partially wired) gets fully wired into chat:

- An agent can call into a delegated agent during its own turn, like a tool call.
- The user sees: the primary agent's response, with a small "✓ consulted [Delegated Agent]" badge near the start. Optional expansion shows the delegated agent's contribution.
- The conversation's *active* agent stays the primary. Delegation is invisible to the conversation's continuity — the user keeps talking to Agent A.

This is distinct from `@-mention agent switching`, which **persistently** changes the conversation's active agent. Both behaviors exist:
- @-mention: "I want to talk to Agent B from now on" — switches.
- Delegation: "Agent A handles it, calling Agent B internally for one part" — invisible.

## 8. Conversation operations

### 8.1 Rename
Click the title in the sidebar to edit inline. Replaces the auto-generated title.

### 8.2 Delete
Soft-delete: sets `is_active=False`, hidden from the sidebar but the DB row is preserved. Hard-delete is admin-only.

### 8.3 Export
"Export" menu item per conversation:
- **Markdown** (default) — formatted message-by-message, with tool calls as collapsible code blocks.
- **JSON** — structured, suitable for re-importing or feeding to other tools.

Workspace-level export (zip of all conversations) is deferred to v2.

## 9. Search

### 9.1 v1 sidebar search
Sidebar gets a search box. Filters conversations by title and `last_message_preview`. Client-side filtering on already-loaded conversation summaries; cheap, no backend changes needed.

### 9.2 v2 (deferred)
Full-text search across message bodies and tool outputs. Requires Postgres FTS index on `messages.content` plus careful permission filtering. Out of scope for this sub-project but not blocked by it.

## 10. Wire format additions

The existing `ChatStreamChunk` union (`api/src/models/contracts/agents.py`) gets new chunk types:

- `compaction_started` — model context is being compacted; UI shows a brief "Compacting older turns..." indicator.
- `compaction_complete` — replaces the in-flight indicator with "Compacted N earlier turns" (passive).
- `delegation_started` — the active agent is delegating to another agent. Includes delegated agent's id/name. UI shows the "✓ consulted" badge being assembled.
- `delegation_complete` — delegated agent finished; result included.

The existing `context_warning` chunk stays but its semantics are now "compaction is approaching/imminent" rather than "messages will be deleted."

## 11. Data model changes

### 11.1 New tables

**workspaces** — fields per §2.2

**message_attachments** — fields per §3.3

**org_model_aliases** — per §5.8

| Field | Type |
|---|---|
| `id` | UUID |
| `org_id` | UUID FK |
| `alias` | str (e.g., `acme-default`) |
| `target_model_id` | str |
| `display_name` | str |
| `cost_tier` | enum |
| `created_at` / `updated_at` | datetime |

**model_deprecations** — per §5.8.3

| Field | Type |
|---|---|
| `old_model_id` | str (PK or unique) |
| `new_model_id` | str |
| `deprecated_at` | datetime |
| `org_id` | UUID NULL — null = platform-wide; set = org-specific override |
| `notes` | str (optional message shown in admin UI) |

### 11.2 Modified tables

**conversations**:
- ADD `workspace_id UUID NOT NULL FK workspaces.id` (default: user's Personal workspace)
- ADD `instructions TEXT NULL` (per §6)
- ADD `current_model VARCHAR NULL` (per §5)

**messages**:
- ADD `model VARCHAR NULL` — already exists, repurposed: the actual model used for this turn.
- ADD `cost_tier VARCHAR NULL` — denormalized from model for easy aggregation.
- (No `parent_message_id` — linear only.)

**orgs** (existing):
- ADD `allowed_chat_models JSONB DEFAULT '[]'` — list of model IDs available for chat in this org.
- ADD `default_chat_model VARCHAR NULL`

**roles** (existing):
- ADD `allowed_chat_models JSONB NULL`
- ADD `default_chat_model VARCHAR NULL`

### 11.3 Migration plan
Single Alembic migration adds all the new tables and columns. Default values backfill cleanly:
- Existing conversations get assigned to the owning user's auto-created Personal workspace.
- Existing messages have no `cost_tier`; populated lazily on next access via the model registry lookup.
- No existing data is destroyed.

## 12. Implementation phases (within this sub-project)

The Chat UX sub-project is itself sizable. To make it tractable in a worktree, split into shippable milestones:

### M1 — Foundations (~1.5 weeks)
- Workspace ORM + API + migration.
- Synthetic "Personal" workspace auto-creation per user on first chat access.
- Sidebar shows workspaces as folders.
- Conversations always live in a workspace.

### M2 — Model resolver + curation (~1 week)
- `api/shared/model_resolver.py` shared utility.
- Org/role/workspace model allowlist fields.
- Platform model registry with cost tiers.
- Chat picker UI with provenance tooltips.
- Conversation `current_model` set by picker; per-message override via retry dropdown.

### M3 — Edit + retry + per-conversation instructions (~0.5 week)
- Edit user message inline.
- Retry last assistant response with optional model override.
- Per-conversation `instructions` field + settings UI.

### M4 — Attachments (~1.5 weeks)
- Upload flow (drag/drop, paperclip, paste from clipboard).
- S3 storage; new `message_attachments` table.
- Server-side text extraction for PDFs.
- Image, PDF, CSV, text rendering in chat.
- Vision content blocks for image-capable models.

### M5 — Compaction (~1 week)
- Lossless summarization replacing the current pruning.
- Per-model-aware threshold via resolver.
- Manual compact button.
- New chunk types in wire format.

### M6 — Multi-agent delegation in chat (~0.5 week)
- Wire `delegated_agent_ids` into `agent_executor.py` as a callable from within a turn.
- New chunk types `delegation_started` / `delegation_complete`.
- "✓ consulted" badge + expandable detail.

### M7 — Polish (~1 week)
- Sidebar search.
- Conversation rename / soft-delete / export.
- Context budget indicator (real-time, model-aware).
- Cost tier badges per message.

**Estimated total: 6-7 weeks of focused work** (compared to the program spec's "4-6 weeks" estimate; the model resolver and workspaces work pushed it higher than I'd initially guessed).

## 13. Testing

Each milestone ships:
- Unit tests for backend logic (`api/tests/unit/`).
- E2E tests for new endpoints (`api/tests/e2e/`).
- Vitest tests for new frontend modules (workspace store, model picker logic, attachment upload helpers, etc.).
- Playwright tests for user-facing flows: create workspace, send chat with attachment, edit user message, switch model mid-conversation, manual compact.

The model resolver gets a thorough unit-test suite — it's the kind of thing where a subtle bug in the intersection logic ships a customer in the wrong tier. Test the chain at every level.

## 14. Cross-cutting concerns (program-wide reminders)

Per the program spec, this sub-project also addresses:

- **Permissions / org control**: workspaces respect scope (personal/org/role); model curation enforces org→role→workspace cascade; tool intersection ensures workspace can restrict but not expand.
- **Cost accounting**: cost tier surfaced in chat (symbolic), dollars in admin dashboard. Per-message tier saved via `messages.cost_tier`. Per-conversation aggregate is a SUM query.
- **Testing**: pre-completion verification (pyright, ruff, tsc, lint, full test suite) is mandatory before merging this sub-project to main.

## 15. Future-proofing for later sub-projects

What this spec leaves as seams for sub-projects (2)–(5):

- **(2) Code Execution** — the model resolver already exists; the new run_code tool will use it. Workspace `enabled_tool_ids` already gates tool availability per workspace. Code Execution becomes "just another tool" with a sandboxed backend (no chat plumbing changes).
- **(3) Skills** — new wire-format chunks (`skill_loaded`, `skill_invoked`) extend `ChatStreamChunk` cleanly. Workspaces can be extended with `enabled_skill_ids` paralleling `enabled_tool_ids` without schema disruption.
- **(4) Artifacts** — workspaces become the natural home; `Workspace.artifacts` relationship added later. Wire format gets new `artifact_created` / `artifact_updated` chunk types.
- **(5) Web Search** — same shape as Code Execution: a tool, gated by workspace's `enabled_tool_ids`. Can also be exposed at the workspace level (e.g., "this workspace's web searches use only the org's approved provider").

## 16. References

- Program spec: `2026-04-27-chat-v2-program-design.md`
- Master plan: `../plans/2026-04-27-chat-v2-master-plan.md`
- Sandbox findings (will matter for sub-project (2)): `2026-04-27-chat-v2-sandbox-bwrap-findings.md`
- Existing chat ORM: `api/src/models/orm/agents.py:166-254`
- Existing chat contracts: `api/src/models/contracts/agents.py:180-435`
- Existing agent executor: `api/src/services/agent_executor.py`
- Existing chat store: `client/src/stores/chatStore.ts`
- Existing upload store (reused for attachments): `client/src/stores/uploadStore.ts`
