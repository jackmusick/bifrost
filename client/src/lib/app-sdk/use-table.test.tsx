import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";

// Capture the latest subscribe callback so tests can drive events.
const subscribeMock = vi.fn();
let lastOnEvent:
  | ((evt: Record<string, unknown>) => void)
  | null = null;

vi.mock("./ws-client", () => ({
  subscribeToTable: (
    _tableId: string,
    _filter: unknown,
    cb: (evt: Record<string, unknown>) => void,
  ) => {
    lastOnEvent = cb;
    subscribeMock(_tableId, _filter, cb);
    return () => {
      lastOnEvent = null;
    };
  },
}));

import { useTable } from "./use-table";

describe("useTable", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    subscribeMock.mockClear();
    lastOnEvent = null;
  });

  it("returns initial snapshot", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ documents: [{ id: "r1", data: { x: 1 } }], total: 1 }),
        {
          status: 200,
          headers: { "content-type": "application/json" },
        },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useTable("t1"));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.rows).toHaveLength(1);
    expect(result.current.rows[0]?.id).toBe("r1");
    expect(result.current.error).toBeNull();
  });

  it("applies inserts from subscribe", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ documents: [], total: 0 }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useTable("t1"));
    await waitFor(() => expect(result.current.loading).toBe(false));
    await waitFor(() => expect(lastOnEvent).not.toBeNull());

    act(() => {
      lastOnEvent?.({
        type: "document_change",
        action: "insert",
        row: { id: "r1", data: { x: 1 } },
        table_id: "t1",
      });
    });

    expect(result.current.rows).toHaveLength(1);
    expect(result.current.rows[0]?.id).toBe("r1");
  });

  it("applies updates by replacing the row with matching id", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          documents: [
            { id: "r1", data: { x: 1 } },
            { id: "r2", data: { x: 2 } },
          ],
          total: 2,
        }),
        {
          status: 200,
          headers: { "content-type": "application/json" },
        },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useTable("t1"));
    await waitFor(() => expect(result.current.loading).toBe(false));
    await waitFor(() => expect(lastOnEvent).not.toBeNull());

    act(() => {
      lastOnEvent?.({
        type: "document_change",
        action: "update",
        row: { id: "r1", data: { x: 99 } },
        table_id: "t1",
      });
    });

    expect(result.current.rows).toHaveLength(2);
    const r1 = result.current.rows.find((r) => r.id === "r1");
    expect((r1?.data as { x: number } | undefined)?.x).toBe(99);
    // r2 untouched
    const r2 = result.current.rows.find((r) => r.id === "r2");
    expect((r2?.data as { x: number } | undefined)?.x).toBe(2);
  });

  it("applies deletes by row_id (covers visibility-loss)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          documents: [
            { id: "r1", data: { x: 1 } },
            { id: "r2", data: { x: 2 } },
          ],
          total: 2,
        }),
        {
          status: 200,
          headers: { "content-type": "application/json" },
        },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useTable("t1"));
    await waitFor(() => expect(result.current.loading).toBe(false));
    await waitFor(() => expect(lastOnEvent).not.toBeNull());

    act(() => {
      lastOnEvent?.({
        type: "document_change",
        action: "delete",
        row_id: "r1",
        table_id: "t1",
      });
    });

    expect(result.current.rows).toHaveLength(1);
    expect(result.current.rows[0]?.id).toBe("r2");
  });

  it("ignores non-document_change events (e.g. subscription_revoked)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ documents: [{ id: "r1", data: {} }], total: 1 }),
        {
          status: 200,
          headers: { "content-type": "application/json" },
        },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useTable("t1"));
    await waitFor(() => expect(result.current.loading).toBe(false));
    await waitFor(() => expect(lastOnEvent).not.toBeNull());

    act(() => {
      lastOnEvent?.({
        type: "subscription_revoked",
        channel: "table:t1",
      });
    });

    expect(result.current.rows).toHaveLength(1);
    expect(result.current.rows[0]?.id).toBe("r1");
  });

  it("subscribes with the same filter passed to the initial query", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ documents: [], total: 0 }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const where = { eq: ["status", "active"] } as unknown as Record<
      string,
      unknown
    >;
    const { result } = renderHook(() =>
      useTable("t1", { where: where as never }),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    await waitFor(() => expect(subscribeMock).toHaveBeenCalled());

    const [tableId, filterArg] = subscribeMock.mock.calls[0];
    expect(tableId).toBe("t1");
    expect(filterArg).toEqual(where);
  });
});
