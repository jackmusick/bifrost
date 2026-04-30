# App Patterns

Mandatory resilience and structure patterns for every Bifrost app. Skipping these produces broken apps.

## 1. Loading & Error States

Every data-fetching page must render a distinct UI for `isLoading` and `isError`.

### `useWorkflowQuery`

```tsx
import { useWorkflowQuery, Alert, AlertTitle, AlertDescription, Skeleton } from "bifrost";
import { Loader2 } from "lucide-react";

export default function ClientsPage() {
  const { data, isLoading, isError, error } = useWorkflowQuery<{ items: any[] }>("uuid-here");

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-5 w-5 animate-spin" />
      </div>
    );
  }
  if (isError) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Error</AlertTitle>
        <AlertDescription>{error ?? "Failed to load"}</AlertDescription>
      </Alert>
    );
  }

  return (
    <ul>
      {data?.items?.map((c) => <li key={c.id}>{c.name}</li>)}
    </ul>
  );
}
```

### Plain `fetch`

```tsx
import { useEffect, useState } from "bifrost";

export default function Page() {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/something")
      .then((r) => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
      .then((json) => { if (!cancelled) setData(json); })
      .catch((e) => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  if (loading) return <div>Loading…</div>;
  if (error) return <div className="text-destructive">{error}</div>;
  return <pre>{JSON.stringify(data, null, 2)}</pre>;
}
```

## 2. Null-safe data access

Workflow results can be null until the execution completes. Use optional chaining and nullish coalescing everywhere.

```tsx
const { data } = useWorkflowQuery<{ items?: Client[] }>("uuid");

// YES — never throws if data / items are null
const count = data?.items?.length ?? 0;
data?.items?.map((c) => <Row key={c.id} name={c.name ?? "Unknown"} />);

// NO — throws on first render
data.items.map(...)           // TypeError: Cannot read properties of null
data.items.length             // TypeError
```

## 3. Mutation error handling

Every `useWorkflowMutation` must handle errors with user feedback and leave the user on the current page unless the mutation succeeds.

```tsx
import { useWorkflowMutation, Button, toast } from "bifrost";

export default function SaveButton({ payload }: { payload: any }) {
  const { execute, isLoading } = useWorkflowMutation("save-uuid");

  async function onClick() {
    try {
      await execute(payload);
      toast.success("Saved");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Save failed");
      // stay on page — user can retry
    }
  }

  return <Button onClick={onClick} disabled={isLoading}>Save</Button>;
}
```

### Optimistic update reversal

If you mutate local state before awaiting the workflow, revert it on error.

```tsx
import { useState, useWorkflowMutation, toast } from "bifrost";

export default function ToggleStar({ item }: { item: { id: string; starred: boolean } }) {
  const [starred, setStarred] = useState(item.starred);
  const { execute } = useWorkflowMutation("toggle-star-uuid");

  async function toggle() {
    const prev = starred;
    setStarred(!prev);            // optimistic
    try {
      await execute({ id: item.id, starred: !prev });
    } catch (e) {
      setStarred(prev);           // revert
      toast.error("Could not update");
    }
  }

  return <button onClick={toggle}>{starred ? "★" : "☆"}</button>;
}
```

## 4. Dependency safety (hooks)

`useEffect` / `useCallback` / `useMemo` dependency arrays must include every referenced external value or you will get stale closures. Never disable the exhaustive-deps rule without understanding why.

```tsx
import { useEffect, useState } from "bifrost";

export default function Search({ q, onChange }: { q: string; onChange: (s: string) => void }) {
  const [local, setLocal] = useState(q);

  // WRONG — missing `q` dep, stale if parent changes q
  // useEffect(() => { setLocal(q); }, []);

  // RIGHT
  useEffect(() => { setLocal(q); }, [q]);

  // RIGHT — debounce pattern, cleanup cancels stale callbacks
  useEffect(() => {
    const h = setTimeout(() => onChange(local), 250);
    return () => clearTimeout(h);
  }, [local, onChange]);

  return <input value={local} onChange={(e) => setLocal(e.target.value)} />;
}
```

## 5. Custom components

Files under `<app>/components/*.tsx` hold app-specific components. Rules:

- One component per file; filename matches the component name (PascalCase).
- Either default export OR named export matching the filename. The bundler detects which.
- Import from sibling files with relative paths: `import SearchInput from "./components/SearchInput"` (from a page) or `import Helper from "./Helper"` (from another component).
- Components CAN reference each other — the bundler handles the dependency graph.
- Components import platform primitives from `"bifrost"`, icons from `"lucide-react"`, router from `"react-router-dom"` — same rules as pages.

```tsx
// apps/my-app/components/ClientCard.tsx
import { Card, CardContent, Badge } from "bifrost";
import { Building2 } from "lucide-react";

export default function ClientCard({ name, status }: { name: string; status: string }) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-3">
        <Building2 className="h-4 w-4" />
        <span className="font-medium flex-1">{name}</span>
        <Badge>{status}</Badge>
      </CardContent>
    </Card>
  );
}
```

```tsx
// apps/my-app/pages/clients/index.tsx
import ClientCard from "../../components/ClientCard";
// …
```

## 6. Code splitting with `React.lazy`

Heavy pages (large dependencies, charts, rich text editors) should be code-split so they don't bloat the initial bundle. The bundler supports `lazy(() => import("./pages/heavy"))` natively — esbuild emits a separate chunk and the browser fetches it on demand.

**When to split:**
- Pages that pull in large user deps (`recharts`, `react-quill-new`, etc.).
- Rarely-visited routes (settings, admin, onboarding wizards).
- Anything that makes first paint slow for common routes.

**When NOT to split:**
- The index route — it always loads; splitting adds one extra round-trip.
- Small pages with only platform imports.

### Pattern

```tsx
// apps/my-app/_layout.tsx
import { Outlet, Suspense, lazy } from "bifrost";
import { Loader2 } from "lucide-react";
import { Route, Routes } from "react-router-dom";

// Index is eager — first paint has no extra round-trip.
import Dashboard from "./pages/index";
// Heavy routes are lazy — separate chunk, fetched on navigation.
const Reports = lazy(() => import("./pages/reports"));
const Editor = lazy(() => import("./pages/editor"));

export default function Layout() {
  return (
    <div className="flex h-full">
      <nav>…</nav>
      <main className="flex-1 min-h-0 overflow-auto">
        <Suspense fallback={<div className="flex h-full items-center justify-center"><Loader2 className="animate-spin" /></div>}>
          <Outlet />
        </Suspense>
      </main>
    </div>
  );
}
```

If your app routes via `<Outlet />` in `_layout.tsx` (the typical case), a single `<Suspense>` around `<Outlet />` covers every lazy child page. If you build your own `<Routes>` tree, wrap it in `<Suspense>`.

## 7. Layout — fixed-height container

Your app renders in a fixed-height box. Manage your own scrolling; do not assume the page body scrolls.

```tsx
// apps/my-app/_layout.tsx
import { Outlet } from "bifrost";

export default function Layout() {
  return (
    <div className="flex h-full">
      <aside className="w-56 shrink-0 border-r">…sidebar…</aside>
      <main className="flex-1 min-w-0 min-h-0 flex flex-col">
        <header className="shrink-0 border-b px-6 py-3">…toolbar…</header>
        <div className="flex-1 min-h-0 overflow-auto p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
```

Key classes:
- `h-full` on the root to claim the container's height.
- `flex-1 min-h-0` on scroll regions — without `min-h-0`, flex children refuse to shrink below their intrinsic content height and overflow escapes the container.
- `overflow-auto` on the innermost scrollable region only.
- `shrink-0` on fixed-height siblings (toolbar, sidebar).

## 8. `useUser` + role guards

### Page-level guard (first line of the component)

```tsx
import { useUser, Navigate } from "bifrost";

export default function AdminPage() {
  const user = useUser();
  if (!user.hasRole("Admin")) return <Navigate to="/" />;
  // …
}
```

### Section-level guard

```tsx
{user.hasRole("Manager") && <AdminPanel />}
```

### Declarative guard

```tsx
import { RequireRole, Navigate } from "bifrost";

<RequireRole role="Admin" fallback={<Navigate to="/" />}>
  <AdminPage />
</RequireRole>
```

### Layout-level guard (protect all child routes)

```tsx
// _layout.tsx
import { Outlet, useUser, Navigate } from "bifrost";

export default function Layout() {
  const user = useUser();
  if (!user.hasRole("Admin")) return <Navigate to="/" />;
  return <div className="flex h-full"><Sidebar /><Outlet /></div>;
}
```

## 9. `useAppState` — cross-page state

Like `useState` but persists across page navigations within the same app session.

```tsx
import { useAppState, Button, useNavigate } from "bifrost";

// List page
export default function ClientsList() {
  const [, setSelected] = useAppState<any>("selectedClient", null);
  const navigate = useNavigate();
  return clients.map((c) => (
    <Button key={c.id} onClick={() => { setSelected(c); navigate("/client-details"); }}>
      {c.name}
    </Button>
  ));
}

// Detail page
import { useAppState, Navigate } from "bifrost";

export default function ClientDetails() {
  const [selected] = useAppState<any>("selectedClient", null);
  if (!selected) return <Navigate to="/" />;
  return <div>{selected.name}</div>;
}
```

Scope: the app session. Cleared on browser refresh or when switching apps. NOT persistent storage — save to DB via workflows for anything that must survive a reload.

## 10. Styling — Tailwind v4 in apps

Apps go through the platform's per-app Tailwind v4 pipeline at bundle time. Everything a normal Tailwind project supports works — including the long-tail features that landed in v4. **Use them.** The platform compiles your app's classes against the host theme; you don't have to remember a list of "what's safe."

### What works

- **All standard utilities**, including the host's shadcn theme tokens (`bg-background`, `bg-card`, `text-muted-foreground`, etc.) — these come from the host preload, available everywhere.
- **Arbitrary values**, including with CSS variables and modern color spaces:
  - `max-w-[1400px]`, `min-h-[calc(100vh-4rem)]`, `px-[clamp(1rem,3vw,2.5rem)]`
  - `lg:grid-cols-[minmax(0,1fr)_360px]`, `md:grid-cols-[repeat(auto-fit,minmax(220px,1fr))]`
  - `bg-[color:var(--ops-paper)]`, `bg-[oklch(0.4_0.1_220)]`, `bg-[hsl(var(--accent)/0.6)]`
- **Responsive variants of arbitrary values:** `lg:py-14`, `xl:grid-cols-[1fr_440px_280px]`
- **`@apply` in `styles.css`**, including with arbitrary values: `.themed { @apply bg-[color:var(--paper)] p-4 rounded; }`
- **`@layer components { .x { @apply ... } }`** for shared component styles.
- **`:root` and `.dark` CSS variable blocks** in `styles.css` — pass through unchanged.
- **Per-app `tailwind.config.{ts,js,mjs,cjs}`** — drop one at the app root and its `theme.extend` is honored. Use this to add custom theme tokens like `theme.extend.colors.brand.500` so `bg-brand-500` compiles.

### Worked example: app with theme tokens, @apply, and per-app config

```css
/* apps/my-app/styles.css */
:root {
  --ops-bg: oklch(0.985 0 0);
  --ops-paper: oklch(1 0 0);
  --ops-fg: oklch(0.145 0 0);
}
.dark {
  --ops-bg: oklch(0.145 0 0);
  --ops-paper: oklch(0.205 0 0);
  --ops-fg: oklch(0.985 0 0);
}

@layer components {
  .ops-pill {
    @apply inline-flex items-center rounded-full px-3 py-1 text-xs font-medium;
  }
}
```

```ts
// apps/my-app/tailwind.config.ts (optional)
export default {
  theme: {
    extend: {
      colors: { brand: { 500: "#facc15" } },
    },
  },
};
```

```tsx
// apps/my-app/pages/index.tsx
export default function Page() {
  return (
    <div className="bg-[color:var(--ops-bg)] text-[color:var(--ops-fg)] min-h-[calc(100vh-4rem)]">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <span className="ops-pill bg-brand-500">Status</span>
      </div>
    </div>
  );
}
```

All four feature classes here (custom CSS variables, `@layer` + `@apply`, per-app theme token, arbitrary-value layout) compile correctly. No workarounds needed.

### Cascade order

The bundler emits the per-app Tailwind output ahead of any other user CSS in the synthesized entry, then user CSS comes after. So host preload < app utilities < user CSS specificity. If you need to override a Tailwind utility, just write the CSS rule.

## 11. Data-heavy app — CRUD with live updates via Tables SDK

Use the Tables SDK (`tables.*` + `useTableSubscription`) when the table has `access` rules configured. No workflow needed for simple reads/writes.

**Table access setup** (run once before building the app):
```bash
# Create the table
bifrost tables create --name tickets --org <uuid>
# Enable access: everyone reads, creator manages their own rows
bifrost tables update --id <table-uuid> --access '{
  "everyone": { "read": true },
  "creator": { "create": true, "update": true, "delete": true }
}'
```

**App: tickets list with insert/edit/delete and live updates**

```tsx
// apps/tickets/pages/index.tsx
import {
  useState, useEffect, useCallback,
  tables, useTableSubscription,
  Button, Input, Dialog, DialogTrigger, DialogContent,
  DialogHeader, DialogTitle, DialogFooter,
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
  toast,
} from "bifrost";
import { Trash2, Pencil } from "lucide-react";

const TABLE = "tickets";          // table name (slug)
const TABLE_UUID = "uuid-here";   // table UUID — resolve with: bifrost tables get tickets --json | jq .id

type Ticket = { id: string; data: { title: string; status: string } };

export default function TicketsPage() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);
  const [editTarget, setEditTarget] = useState<Ticket | null>(null);
  const [title, setTitle] = useState("");

  const load = useCallback(() => {
    setLoading(true);
    tables.query(TABLE)
      .then((r) => setTickets(r.items as Ticket[]))
      .catch(() => toast.error("Failed to load"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  // Live updates — skip reload; patch local state directly
  useTableSubscription(TABLE_UUID, (evt) => {
    if (evt.type !== "document_change") return;
    setTickets((prev) => {
      if (evt.action === "insert" && evt.data)
        return [{ id: evt.id, data: evt.data as Ticket["data"] }, ...prev];
      if (evt.action === "update" && evt.data)
        return prev.map((t) => t.id === evt.id ? { ...t, data: evt.data as Ticket["data"] } : t);
      if (evt.action === "delete")
        return prev.filter((t) => t.id !== evt.id);
      return prev;
    });
  });

  async function create() {
    if (!title.trim()) return;
    try {
      await tables.insert(TABLE, { title, status: "open" });
      setTitle("");
      // subscription delivers the insert
    } catch {
      toast.error("Could not create ticket");
    }
  }

  async function save() {
    if (!editTarget) return;
    try {
      await tables.update(TABLE, editTarget.id, { ...editTarget.data, title });
      setEditTarget(null);
    } catch {
      toast.error("Could not save");
    }
  }

  async function remove(id: string) {
    try {
      await tables.delete(TABLE, id);
    } catch {
      toast.error("Could not delete");
    }
  }

  if (loading) return <div className="flex h-full items-center justify-center">Loading…</div>;

  return (
    <div className="flex flex-col h-full min-h-0">
      <header className="shrink-0 flex gap-2 border-b p-4">
        <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="New ticket…" />
        <Button onClick={create}>Add</Button>
      </header>
      <div className="flex-1 min-h-0 overflow-auto">
        <Table>
          <TableHeader>
            <TableRow><TableHead>Title</TableHead><TableHead>Status</TableHead><TableHead /></TableRow>
          </TableHeader>
          <TableBody>
            {tickets.map((t) => (
              <TableRow key={t.id}>
                <TableCell>{t.data.title}</TableCell>
                <TableCell>{t.data.status}</TableCell>
                <TableCell className="flex gap-1">
                  <Dialog open={editTarget?.id === t.id} onOpenChange={(o) => { if (!o) setEditTarget(null); }}>
                    <DialogTrigger asChild>
                      <Button variant="ghost" size="icon" onClick={() => { setEditTarget(t); setTitle(t.data.title); }}>
                        <Pencil className="h-4 w-4" />
                      </Button>
                    </DialogTrigger>
                    <DialogContent>
                      <DialogHeader><DialogTitle>Edit ticket</DialogTitle></DialogHeader>
                      <Input value={title} onChange={(e) => setTitle(e.target.value)} />
                      <DialogFooter><Button onClick={save}>Save</Button></DialogFooter>
                    </DialogContent>
                  </Dialog>
                  <Button variant="ghost" size="icon" onClick={() => remove(t.id)}>
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
```

Key points:
- `useTableSubscription` patches local state on each event — no full reload on every change.
- `creator.create/update/delete` means each user only mutates their own rows; `everyone.read` lets all users see the full list.
- Replace `TABLE_UUID` with the UUID from `bifrost tables get tickets --json | jq -r .id`.
- To use a workflow instead (e.g. for email notifications on create), swap `tables.insert(...)` for `execute(...)` from `useWorkflowMutation` — the subscription still delivers live updates.

### What's still NOT supported

- Tailwind plugins beyond `@tailwindcss/typography` (which the host already provides via the preload). The bundler's compile pass uses the default v4 plugin set; per-app `plugins: [...]` arrays in `tailwind.config.ts` are ignored.
- `@source` directives to scan files outside the app root. The bundler scans the app's own materialized source tree only.
