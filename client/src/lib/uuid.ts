/**
 * UUID helpers.
 *
 * `crypto.randomUUID` is only exposed in secure contexts (HTTPS, localhost,
 * 127.0.0.1). Plain-HTTP debug stacks (e.g. our Netbird mesh URL) don't
 * qualify, so the native API throws `TypeError: crypto.randomUUID is not a
 * function` there. This wrapper falls back to `crypto.getRandomValues` —
 * available in any non-prehistoric browser regardless of secure-context
 * status — to produce an RFC4122 v4 UUID.
 *
 * Use this wrapper for any in-browser UUID generation. Direct calls to
 * `crypto.randomUUID()` will break the app in non-HTTPS environments.
 */

const HEX_BYTE: string[] = [];
for (let i = 0; i < 256; i++) {
	HEX_BYTE.push((i + 0x100).toString(16).slice(1));
}

export function safeRandomUUID(): string {
	if (
		typeof crypto !== "undefined" &&
		typeof crypto.randomUUID === "function"
	) {
		return crypto.randomUUID();
	}
	const bytes = new Uint8Array(16);
	crypto.getRandomValues(bytes);
	bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
	bytes[8] = (bytes[8] & 0x3f) | 0x80; // variant 10xx
	return (
		HEX_BYTE[bytes[0]] +
		HEX_BYTE[bytes[1]] +
		HEX_BYTE[bytes[2]] +
		HEX_BYTE[bytes[3]] +
		"-" +
		HEX_BYTE[bytes[4]] +
		HEX_BYTE[bytes[5]] +
		"-" +
		HEX_BYTE[bytes[6]] +
		HEX_BYTE[bytes[7]] +
		"-" +
		HEX_BYTE[bytes[8]] +
		HEX_BYTE[bytes[9]] +
		"-" +
		HEX_BYTE[bytes[10]] +
		HEX_BYTE[bytes[11]] +
		HEX_BYTE[bytes[12]] +
		HEX_BYTE[bytes[13]] +
		HEX_BYTE[bytes[14]] +
		HEX_BYTE[bytes[15]]
	);
}
