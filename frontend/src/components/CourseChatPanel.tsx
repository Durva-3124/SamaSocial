import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import type { CourseMessage } from "../hooks/useCourse";
import "./CourseChatPanel.css";

interface Props {
  messages: CourseMessage[];
  streaming: boolean;
  missing: string[];
  error: string | null;
  onSend: (text: string) => void;
}

export default function CourseChatPanel({ messages, streaming, missing, error, onSend }: Props) {
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");
    onSend(text);
  }

  return (
    <section className="ccp">
      {missing.length > 0 && (
        <div className="ccp-missing">
          Still needed: <strong>{missing.join(", ")}</strong>
        </div>
      )}

      <div className="ccp-messages">
        {messages.length === 0 && (
          <p className="ccp-empty">
            Tell me what you want to learn — topic, goal, level, timeline.
          </p>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`ccp-bubble ccp-bubble--${msg.role}`}>
            <ReactMarkdown>
              {msg.content || (msg.role === "assistant" && streaming ? "▌" : "")}
            </ReactMarkdown>
          </div>
        ))}
        {error && <p className="ccp-error">{error}</p>}
        <div ref={bottomRef} />
      </div>

      <form className="ccp-form" onSubmit={handleSubmit}>
        <input
          className="ccp-input"
          type="text"
          placeholder="Describe your learning goal…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={streaming}
        />
        <button
          className="btn btn--primary"
          type="submit"
          disabled={streaming || !input.trim()}
        >
          {streaming ? "…" : "Send"}
        </button>
      </form>
    </section>
  );
}
