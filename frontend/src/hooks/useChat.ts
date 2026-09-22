import { useCallback, useEffect, useRef, useState } from "react";
import { openChatStream, type CitationItem } from "../api/sessions";
import { SseParser } from "../lib/sse";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: CitationItem[];
  declined?: boolean;
}

export interface UseChatReturn {
  messages: ChatMessage[];
  streaming: boolean;
  error: string | null;
  sendMessage: (sessionId: string, text: string, mode: "normal" | "simple") => Promise<void>;
  stop: () => void;
}

let _msgCounter = 0;
function nextId() {
  return `msg-${++_msgCounter}`;
}

export function useChat(): UseChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);
  }, []);

  useEffect(() => () => { abortRef.current?.abort(); }, []);

  const sendMessage = useCallback(
    async (sessionId: string, text: string, mode: "normal" | "simple") => {
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;

      setError(null);

      const userId = nextId();
      const assistantId = nextId();
      setMessages((prev) => [
        ...prev,
        { id: userId, role: "user", content: text },
        { id: assistantId, role: "assistant", content: "" },
      ]);
      setStreaming(true);

      const parser = new SseParser();
      let fullContent = "";

      try {
        const reader = openChatStream(sessionId, text, mode, ctrl.signal);
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          for (const { event, data } of parser.push(value)) {
            if (event === "token") {
              fullContent += data.text as string;
              const snapshot = fullContent;
              setMessages((prev) =>
                prev.map((m) => (m.id === assistantId ? { ...m, content: snapshot } : m)),
              );
            } else if (event === "citations") {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, citations: data.items as CitationItem[] }
                    : m,
                ),
              );
            } else if (event === "done") {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId ? { ...m, declined: data.declined as boolean } : m,
                ),
              );
            } else if (event === "error") {
              setError(data.message as string);
            }
          }
        }
      } catch (e: unknown) {
        if ((e as Error)?.name !== "AbortError") {
          setError(e instanceof Error ? e.message : "Chat failed");
        }
      } finally {
        if (abortRef.current === ctrl) abortRef.current = null;
        setStreaming(false);
      }
    },
    [],
  );

  return { messages, streaming, error, sendMessage, stop };
}
