import { render, screen } from "@testing-library/react";
import { StrictMode, useEffect } from "react";
import { describe, expect, it, vi } from "vitest";

import { BifrostProvider, useBifrostContext } from "./provider";
import { getBifrostTransport } from "./tables";

function Probe() {
  const c = useBifrostContext();
  return (
    <span data-testid="probe">
      {c.baseUrl}|{c.token}|{c.orgScope ?? "none"}
    </span>
  );
}

describe("BifrostProvider", () => {
  it("provides baseUrl, token, and orgScope via context", () => {
    render(
      <BifrostProvider baseUrl="https://dev.example" token="tok-123" orgScope="org-9">
        <Probe />
      </BifrostProvider>,
    );
    expect(screen.getByTestId("probe").textContent).toBe(
      "https://dev.example|tok-123|org-9",
    );
  });

  it("defaults orgScope to null when omitted", () => {
    render(
      <BifrostProvider baseUrl="https://dev.example" token="tok-123">
        <Probe />
      </BifrostProvider>,
    );
    expect(screen.getByTestId("probe").textContent).toBe(
      "https://dev.example|tok-123|none",
    );
  });

  it("exposes an authed fetch that attaches the bearer token and base url", async () => {
    let captured: { url: string; auth: string | null } | null = null;
    const fakeFetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const headers = new Headers(init?.headers);
      captured = { url: String(input), auth: headers.get("Authorization") };
      return new Response("{}", { status: 200 });
    }) as typeof fetch;

    function Caller() {
      const { authedFetch } = useBifrostContext();
      // fire on render
      void authedFetch("/api/workflows/run");
      return <span>called</span>;
    }

    render(
      <BifrostProvider baseUrl="https://dev.example" token="tok-abc" fetchImpl={fakeFetch}>
        <Caller />
      </BifrostProvider>,
    );
    // microtask flush
    await Promise.resolve();
    expect(captured).not.toBeNull();
    expect(captured!.url).toBe("https://dev.example/api/workflows/run");
    expect(captured!.auth).toBe("Bearer tok-abc");
  });

  it("routes the table SDK through baseUrl + bearer while mounted", async () => {
    const { tables } = await import("./tables");
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ id: "r", data: {} }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );

    const { unmount } = render(
      <BifrostProvider
        baseUrl="https://dev.example"
        token="tok-1"
        fetchImpl={fetchMock as unknown as typeof fetch}
      >
        <span>ok</span>
      </BifrostProvider>,
    );

    await tables.get("notes", "r");
    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toBe("https://dev.example/api/tables/notes/documents/r");

    // After unmount the transport is restored (same-origin default).
    unmount();
    const globalFetch = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ id: "r", data: {} }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", globalFetch);
    await tables.get("notes", "r");
    expect(globalFetch.mock.calls[0][0]).toBe("/api/tables/notes/documents/r");
  });

  it("installs the transport before child mount effects run", () => {
    // A child's mount effect (e.g. useTable's first snapshot query) runs
    // BEFORE the provider's own useEffect. The transport must already be the
    // provider's by then, or the first query goes out same-origin unauthed.
    const seen: string[] = [];
    function TransportProbe() {
      useEffect(() => {
        seen.push(getBifrostTransport().baseUrl);
      }, []);
      return null;
    }
    render(
      <BifrostProvider baseUrl="https://remote.example" token="tok-eff">
        <TransportProbe />
      </BifrostProvider>,
    );
    expect(seen.length).toBeGreaterThan(0);
    expect(seen[0]).toBe("https://remote.example");
  });

  it("keeps the transport installed under StrictMode and restores on unmount", () => {
    // StrictMode runs mount → cleanup → mount; the cleanup must not leave the
    // transport reset to the default while the provider is still mounted.
    const { unmount } = render(
      <StrictMode>
        <BifrostProvider baseUrl="https://strict.example" token="tok-sm">
          <span>ok</span>
        </BifrostProvider>
      </StrictMode>,
    );
    expect(getBifrostTransport().baseUrl).toBe("https://strict.example");
    unmount();
    expect(getBifrostTransport().baseUrl).toBe("");
  });

  it("throws a clear error when used outside a provider", () => {
    function Orphan() {
      useBifrostContext();
      return null;
    }
    // suppress React error boundary console noise
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Orphan />)).toThrow(/BifrostProvider/);
    spy.mockRestore();
  });
});
