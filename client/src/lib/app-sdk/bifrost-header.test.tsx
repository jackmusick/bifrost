import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BifrostHeader } from "./bifrost-header";
import { BifrostProvider } from "./provider";

describe("BifrostHeader (SDK, self-contained)", () => {
  it("renders the title + back-to-Bifrost link and logs out via the user menu", () => {
    const onLogout = vi.fn();
    render(
      <BifrostProvider baseUrl="https://dev.example" token="t" onLogout={onLogout}>
        <BifrostHeader title="My Dashboard" />
      </BifrostProvider>,
    );
    expect(screen.getByText("My Dashboard")).toBeInTheDocument();
    const back = screen.getByRole("link", { name: /Bifrost/i });
    expect(back.getAttribute("href")).toBe("https://dev.example/");

    // Log out lives inside the user-menu dropdown now — open it first.
    fireEvent.click(screen.getByRole("button", { name: /account menu/i }));
    fireEvent.click(screen.getByRole("menuitem", { name: /log out/i }));
    expect(onLogout).toHaveBeenCalledTimes(1);
  });

  it("shows the theme toggle ONLY when the app opts in via supportsTheme", () => {
    const { rerender } = render(
      <BifrostProvider baseUrl="https://dev.example" token="t">
        <BifrostHeader title="X" />
      </BifrostProvider>,
    );
    // Default: app did not declare supportsTheme → no toggle.
    expect(screen.queryByRole("button", { name: /theme/i })).toBeNull();

    rerender(
      <BifrostProvider baseUrl="https://dev.example" token="t" supportsTheme>
        <BifrostHeader title="X" />
      </BifrostProvider>,
    );
    expect(screen.getByRole("button", { name: /theme/i })).toBeInTheDocument();
  });

  it("renders an optional action slot", () => {
    render(
      <BifrostProvider baseUrl="https://dev.example" token="t">
        <BifrostHeader title="X" action={<span>extra</span>} />
      </BifrostProvider>,
    );
    expect(screen.getByText("extra")).toBeInTheDocument();
  });

  it("styles itself inline (no dependency on Tailwind/theme CSS variables)", () => {
    // Standalone apps may have no Tailwind build and none of the platform's
    // theme CSS variables. The header must carry its own visual styling so it
    // is not unstyled there. Pin that the chrome comes from inline styles, not
    // semantic Tailwind utility classes that would resolve to nothing.
    const { container } = render(
      <BifrostProvider baseUrl="https://dev.example" token="t">
        <BifrostHeader title="Styled" />
      </BifrostProvider>,
    );
    const header = container.querySelector("header");
    expect(header).not.toBeNull();
    // Layout + chrome is inline, not class-driven.
    expect(header!.style.display).toBe("flex");
    expect(header!.style.borderBottom).not.toBe("");
    // The header must NOT rely on the platform theme tokens that break standalone.
    expect(header!.className).not.toMatch(/text-muted-foreground|bg-accent|border-b\b/);
    // The hover stylesheet is injected and scoped so it can't leak into the host.
    const injected = document.getElementById("bifrost-header-style");
    expect(injected).not.toBeNull();
    expect(injected!.textContent).toContain("[data-bifrost-header]");
  });

  it("still allows author className overrides (applied alongside inline styles)", () => {
    const { container } = render(
      <BifrostProvider baseUrl="https://dev.example" token="t">
        <BifrostHeader title="X" className="my-custom-class" />
      </BifrostProvider>,
    );
    const header = container.querySelector("header");
    expect(header!.className).toContain("my-custom-class");
    // Inline styling is still present (override augments, doesn't replace).
    expect(header!.style.display).toBe("flex");
  });
});
