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
