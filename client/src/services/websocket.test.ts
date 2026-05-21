import { afterEach, describe, expect, it, vi } from "vitest";
import { sanitizeLogText, webSocketService } from "./websocket";

describe("webSocketService security hardening", () => {
	afterEach(() => {
		vi.restoreAllMocks();
	});

	it("sanitizes control characters before logging", () => {
		expect(sanitizeLogText("first\nsecond\rthird\tfourth")).toBe(
			"first second third fourth",
		);
	});

	it("dispatches git operation completion through registered callbacks", () => {
		const service = webSocketService as unknown as {
			handleMessage: (message: unknown) => void;
		};
		const callback = vi.fn();

		const unsubscribe = webSocketService.onGitOpComplete("job-1", callback);
		service.handleMessage({
			type: "git_op_complete",
			jobId: "job-1",
			status: "success",
			resultType: "status",
			data: { clean: true },
		});

		expect(callback).toHaveBeenCalledWith({
			status: "success",
			resultType: "status",
			data: { clean: true },
			error: undefined,
		});

		unsubscribe();
	});

	it("logs notification receipt without dumping attacker-controlled payloads", () => {
		const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
		const service = webSocketService as unknown as {
			handleMessage: (message: unknown) => void;
		};

		service.handleMessage({
			type: "notification_created",
			notification: {
				id: "note-1\nforged",
				category: "system",
				title: "title",
				description: "description",
				status: "running\rforged",
				percent: null,
				error: null,
				result: null,
				metadata: { untrusted: "\nforged" },
				created_at: "2026-05-21T00:00:00Z",
				updated_at: "2026-05-21T00:00:00Z",
				user_id: "user-1",
			},
		});

		expect(warnSpy).toHaveBeenCalledWith("[WS] Notification received");
		expect(warnSpy.mock.calls[0]).toHaveLength(1);
	});
});
