import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { VerdictToggle } from "./verdict-toggle";

describe("VerdictToggle", () => {
  it("calls onChange('up') when up button clicked from null", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<VerdictToggle value={null} onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: /mark as good/i }));
    expect(onChange).toHaveBeenCalledWith("up");
  });

  it("calls onChange('down') when down button clicked from null", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<VerdictToggle value={null} onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: /mark as bad/i }));
    expect(onChange).toHaveBeenCalledWith("down");
  });

  it("clicking the active verdict toggles it back to null", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<VerdictToggle value="up" onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: /mark as good/i }));
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("clicking opposite verdict switches", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<VerdictToggle value="up" onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: /mark as bad/i }));
    expect(onChange).toHaveBeenCalledWith("down");
  });

  it("aria-pressed reflects active state", () => {
    render(<VerdictToggle value="up" onChange={() => {}} />);
    expect(screen.getByRole("button", { name: /mark as good/i })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /mark as bad/i })).toHaveAttribute("aria-pressed", "false");
  });

  it("does not fire onChange when disabled", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<VerdictToggle value={null} onChange={onChange} disabled />);
    await user.click(screen.getByRole("button", { name: /mark as good/i }));
    expect(onChange).not.toHaveBeenCalled();
  });
});
