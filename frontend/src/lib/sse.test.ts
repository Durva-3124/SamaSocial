import { describe, expect, it } from "vitest";
import { SseParser } from "./sse";

function enc(s: string): Uint8Array {
  return new TextEncoder().encode(s);
}

describe("SseParser", () => {
  it("parses a single complete event in one chunk", () => {
    const p = new SseParser();
    const events = p.push(enc("event: token\ndata: {\"text\":\"hi\"}\n\n"));
    expect(events).toHaveLength(1);
    expect(events[0]).toEqual({ event: "token", data: { text: "hi" } });
  });

  it("handles an event split across two chunks", () => {
    const p = new SseParser();
    const first = p.push(enc("event: token\ndata: {"));
    expect(first).toHaveLength(0);

    const second = p.push(enc("\"text\":\"hello\"}\n\n"));
    expect(second).toHaveLength(1);
    expect(second[0]).toEqual({ event: "token", data: { text: "hello" } });
  });

  it("handles several events in one chunk", () => {
    const p = new SseParser();
    const raw =
      "event: token\ndata: {\"text\":\"a\"}\n\n" +
      "event: token\ndata: {\"text\":\"b\"}\n\n" +
      "event: done\ndata: {\"declined\":false}\n\n";
    const events = p.push(enc(raw));
    expect(events).toHaveLength(3);
    expect(events[0].data).toEqual({ text: "a" });
    expect(events[1].data).toEqual({ text: "b" });
    expect(events[2].data).toEqual({ declined: false });
  });

  it("handles multi-byte UTF-8 characters split across chunks", () => {
    // '€' is U+20AC, encoded as 3 bytes: 0xE2 0x82 0xAC
    const full = new TextEncoder().encode("event: token\ndata: {\"text\":\"\u20ac\"}\n\n");
    const splitAt = full.indexOf(0xe2);
    const p = new SseParser();
    const first = p.push(full.slice(0, splitAt + 1));
    expect(first).toHaveLength(0);
    const second = p.push(full.slice(splitAt + 1));
    expect(second).toHaveLength(1);
    expect(second[0].data).toEqual({ text: "\u20ac" });
  });

  it("ignores unknown event types without throwing", () => {
    const p = new SseParser();
    const raw =
      "event: heartbeat\ndata: {}\n\n" +
      "event: token\ndata: {\"text\":\"x\"}\n\n";
    const events = p.push(enc(raw));
    expect(events).toHaveLength(2);
    expect(events[0].event).toBe("heartbeat");
    expect(events[1].event).toBe("token");
  });

  it("ignores blocks with missing event or data lines", () => {
    const p = new SseParser();
    // first block is a comment-only line (no event/data) — should be skipped
    const raw =
      ": keep-alive\n\n" +
      "event: done\ndata: {\"declined\":false}\n\n";
    const events = p.push(enc(raw));
    expect(events).toHaveLength(1);
    expect(events[0].event).toBe("done");
  });

  it("flush returns nothing when buffer is empty", () => {
    const p = new SseParser();
    expect(p.flush()).toHaveLength(0);
  });
});
