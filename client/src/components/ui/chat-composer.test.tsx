import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ChatComposer } from "./chat-composer";

describe("ChatComposer", () => {
  it("calls onSend on Enter (no shift)", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<ChatComposer placeholder="say something" onSend={onSend} />);
    const ta = screen.getByPlaceholderText("say something");
    await user.click(ta);
    await user.keyboard("hi{Enter}");
    expect(onSend).toHaveBeenCalledWith("hi");
  });

  it("does NOT call onSend on Shift+Enter", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<ChatComposer placeholder="say something" onSend={onSend} />);
    const ta = screen.getByPlaceholderText("say something");
    await user.click(ta);
    await user.keyboard("hi{Shift>}{Enter}{/Shift}");
    expect(onSend).not.toHaveBeenCalled();
  });

  it("clears the textarea after sending", async () => {
    const user = userEvent.setup();
    render(<ChatComposer onSend={() => {}} />);
    const ta = screen.getByRole("textbox");
    await user.type(ta, "hello{Enter}");
    expect(ta).toHaveValue("");
  });

  it("disables send when value is empty", () => {
    render(<ChatComposer onSend={() => {}} />);
    expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  });

  it("disables send while pending", () => {
    render(<ChatComposer onSend={() => {}} pending />);
    expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  });

  it("clicking send button submits the value", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<ChatComposer onSend={onSend} />);
    await user.type(screen.getByRole("textbox"), "click test");
    await user.click(screen.getByRole("button", { name: /send/i }));
    expect(onSend).toHaveBeenCalledWith("click test");
  });
});
