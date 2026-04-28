# Chat V2 UX preview

Standalone Vite app that prototypes the Chat V2 sub-project (1) UX surfaces. Imports Bifrost's shadcn/ui primitives and design tokens via symlinks (so the look matches production), but mocks all data and APIs so it runs independently of the dev stack.

## Run

```bash
cd client/preview/chat-v2-ux
npm install
npm run dev    # listens on 0.0.0.0:5174
```

Visit at `http://localhost:5174/` (or `http://development:5174/` over Netbird).

## Routes

| Route | Surface |
|---|---|
| `/` | Index of all surfaces |
| `/full` | Full chat composed (sidebar + chat + floating composer) |
| `/sidebar` | Global sidebar (primary nav + pinned + recent) |
| `/workspace-settings` | Workspace mode (re-scoped sidebar + right rail with context) |
| `/header` | Chat header (model pill + budget bar + cost tier strip) |
| `/picker` | Model picker (aliases + restricted with provenance) |
| `/admin-settings` | Org admin AI settings (table + orphan-reference dialog) |
| `/attachments` | Floating composer with attachment chips + drag-drop overlay |
| `/edit-retry` | Edit message + retry with model override |
| `/compaction` | Inline ChatSystemEvent for "Compacted N earlier turns" |
| `/delegation` | Inline delegation card embedded in primary agent's response |

## Reference

- Spec: `docs/superpowers/specs/2026-04-27-chat-ux-design.md` §16
- Program: `docs/superpowers/specs/2026-04-27-chat-v2-program-design.md`
- Master plan: `docs/superpowers/plans/2026-04-27-chat-v2-master-plan.md`

## Architecture notes

- `src/components/ui` is a **symlink** to `client/src/components/ui` so shadcn primitives stay in sync with production.
- `src/lib` and `src/hooks` are also symlinks for the same reason.
- `src/index.css` is a symlink so design tokens (OKLch teal, radius, etc.) match.
- Preview-specific components (e.g. `Composer.tsx`) live in `src/components/` (not symlinked) so editing them doesn't pollute production.
- All data is mocked in `src/mock.ts`. No API client, no auth, no websockets.
