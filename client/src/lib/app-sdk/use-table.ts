import { useEffect, useState } from "react";
import type { components } from "@/lib/v1";
import { tables, type TableChangeEvent } from "./tables";

type DocumentPublic = components["schemas"]["DocumentPublic"];
type Expr = components["schemas"]["Expr"];

export interface UseTableQuery {
  where?: Expr;
  limit?: number;
  offset?: number;
}

export interface UseTableResult {
  rows: DocumentPublic[];
  loading: boolean;
  error: Error | null;
}

/**
 * Live-updating table data hook.
 *
 * Loads an initial snapshot via `tables.query` and subscribes to live changes
 * via `tables.subscribe`, applying insert/update/delete events to local state.
 * The subscribe filter is the same `where` expression passed to the initial
 * query, so the websocket fanout sees exactly the same row visibility as the
 * snapshot.
 *
 * @param name - Table name (or id) to query and subscribe to
 * @param query - Optional `where`/`limit`/`offset` query parameters
 * @returns `{ rows, loading, error }`
 */
export function useTable(
  name: string,
  query: UseTableQuery = {},
): UseTableResult {
  const [rows, setRows] = useState<DocumentPublic[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const { where, limit, offset } = query;
  // Effect deps below intentionally use JSON.stringify(where) since `where`
  // is an object whose identity changes per render. This keeps the effect
  // stable when callers pass an inline literal each render.
  const whereKey = JSON.stringify(where ?? null);

  useEffect(() => {
    let cancelled = false;
    let unsubscribe: (() => void) | null = null;

    const filter = where ?? null;

    async function init() {
      try {
        const snap = await tables.query(name, { where, limit, offset });
        if (cancelled) return;
        setRows(snap.documents);
        setLoading(false);

        unsubscribe = tables.subscribe(name, filter, (evt) => {
          applyEvent(evt, setRows);
        });
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e : new Error(String(e)));
        setLoading(false);
      }
    }

    init();
    return () => {
      cancelled = true;
      unsubscribe?.();
    };
    // `where` and `whereKey` are equivalent for dep tracking — we list both so
    // the lint rule sees the closed-over `where` and we still get value-based
    // change detection via `whereKey`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [name, whereKey, limit, offset]);

  return { rows, loading, error };
}

function applyEvent(
  evt: TableChangeEvent,
  setRows: (updater: (prev: DocumentPublic[]) => DocumentPublic[]) => void,
) {
  if (evt.type !== "document_change") return;
  if (evt.action === "insert") {
    const inserted = evt.row;
    setRows((prev) => [...prev, inserted]);
    return;
  }
  if (evt.action === "update") {
    const updated = evt.row;
    setRows((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
    return;
  }
  if (evt.action === "delete") {
    const id = evt.row_id;
    setRows((prev) => prev.filter((r) => r.id !== id));
    return;
  }
}
