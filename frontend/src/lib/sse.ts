/**
 * Stateful SSE parser.
 *
 * Feed raw Uint8Array chunks from a ReadableStream via `push(chunk)`.
 * Each call returns an array of fully-parsed `{ event, data }` objects.
 * Incomplete events are held in an internal buffer until the next push.
 *
 * Handles:
 *  - events split across multiple chunks
 *  - multiple events in a single chunk
 *  - multi-byte UTF-8 characters split across chunk boundaries
 *  - unknown / comment lines (silently ignored)
 */
export interface SseEvent {
  event: string;
  data: Record<string, unknown>;
}

export class SseParser {
  private readonly _decoder = new TextDecoder();
  private _buf = "";

  push(chunk: Uint8Array): SseEvent[] {
    this._buf += this._decoder.decode(chunk, { stream: true });
    const events: SseEvent[] = [];

    const blocks = this._buf.split("\n\n");
    // Last element is an incomplete block (or empty string after a trailing \n\n)
    this._buf = blocks.pop() ?? "";

    for (const block of blocks) {
      const lines = block.split("\n");
      let eventName = "";
      let dataStr = "";
      for (const line of lines) {
        if (line.startsWith("event: ")) eventName = line.slice(7).trim();
        else if (line.startsWith("data: ")) dataStr = line.slice(6);
        // comment lines (starting with ':') and unknown fields are ignored
      }
      if (!eventName || !dataStr) continue;
      try {
        events.push({ event: eventName, data: JSON.parse(dataStr) as Record<string, unknown> });
      } catch {
        // malformed JSON — skip
      }
    }

    return events;
  }

  /** Flush any remaining buffered text (call after the stream ends). */
  flush(): SseEvent[] {
    if (!this._buf.trim()) return [];
    // Treat remaining buffer as a complete block
    return this.push(new Uint8Array(0));
  }
}
