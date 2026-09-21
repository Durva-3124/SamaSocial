import { useCallback, useState } from "react";
import { openChatStream, type CitationItem } from "../api/sessions";

export interface ChatMessage {
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
}

export function useChat(): UseChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sendMessage = useCallback(
    async (sessionId: string, text: string, mode: "normal" | "simple") => {
      setError(null);
      setMessages((prev) => [...prev, { role: "user", content: text }]);

      const assistantIdx = messages.length + 1;
      setMessages((prev) => [...prev, { role: "assistant", content: "" }]);
      setStreaming(true);

      const decoder = new TextDecoder();
      let buffer = "";
      let fullContent = "";

      try {
        const reader = openChatStream(sessionId, text, mode);
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const blocks = buffer.split("\n\n");
          buffer = blocks.pop() ?? "";

          for (const block of blocks) {
            const eventLine = block.split("\n").find((l) => l.startsWith("event: "));
            const dataLine = block.split("\n").find((l) => l.startsWith("data: "));
            if (!eventLine || !dataLine) continue;

            const event = eventLine.slice(7).trim();
            const data = JSON.parse(dataLine.slice(6));

            if (event === "token") {
              fullContent += data.text as string;
              setMessages((prev) => {
                const next = [...prev];
                next[assistantIdx] = { ...next[assistantIdx], content: fullContent };
                return next;
              });
            } else if (event === "citations") {
              setMessages((prev) => {
                const next = [...prev];
                next[assistantIdx] = {
                  ...next[assistantIdx],
                  citations: data.items as CitationItem[],
                };
                return next;
              });
            } else if (event === "done") {
              setMessages((prev) => {
                const next = [...prev];
                next[assistantIdx] = {
                  ...next[assistantIdx],
                  declined: data.declined as boolean,
                };
                return next;
              });
            } else if (event === "error") {
              setError(data.message as string);
            }
          }
        }
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Chat failed");
      } finally {
        setStreaming(false);
      }
    },
    [messages.length],
  );

  return { messages, streaming, error, sendMessage };
}
