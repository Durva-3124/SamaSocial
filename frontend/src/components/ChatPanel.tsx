import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import type { ChatMessage } from "../hooks/useChat";
import "./ChatPanel.css";

interface Props {
  messages: ChatMessage[];
  streaming: boolean;
  error: string | null;
  disabled: boolean;
  onSend: (text: string, mode: "normal" | "simple") => void;
}

export default function ChatPanel({ messages, streaming, error, disabled, onSend }: Props) {
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<"normal" | "simple">("normal");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || streaming || disabled) return;
    setInput("");
    onSend(text, mode);
  }

  return (
    <section className="chat-panel">
      <div className="chat-messages">
        {messages.length === 0 && (
          <p className="chat-empty">Ask a question about your sources.</p>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`chat-bubble chat-bubble--${msg.role}`}>
            <ReactMarkdown>{msg.content || (msg.role === "assistant" && streaming ? "▌" : "")}</ReactMarkdown>
            {msg.citations && msg.citations.length > 0 && (
              <ul className="citations">
                {msg.citations.map((c) => (
                  <li key={c.label} className="citation">
                    <span className="citation__label">[{c.label}]</span>
                    <span className="citation__source">{c.source_name}</span>
                    {c.locator_text && (
                      <span className="citation__locator">{c.locator_text}</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {msg.declined && (
              <p className="chat-declined">
                ⚠️ Not enough information in your sources to answer this question.
              </p>
            )}
          </div>
        ))}
        {error && <p className="chat-error">{error}</p>}
        <div ref={bottomRef} />
      </div>

      <form className="chat-form" onSubmit={handleSubmit}>
        <select
          className="chat-mode"
          value={mode}
          onChange={(e) => setMode(e.target.value as "normal" | "simple")}
          disabled={streaming}
        >
          <option value="normal">Normal</option>
          <option value="simple">Simple</option>
        </select>
        <input
          className="chat-input"
          type="text"
          placeholder={disabled ? "Add a source first…" : "Ask a question…"}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={disabled || streaming}
        />
        <button
          className="btn btn--primary"
          type="submit"
          disabled={disabled || streaming || !input.trim()}
        >
          {streaming ? "…" : "Send"}
        </button>
      </form>
    </section>
  );
}
