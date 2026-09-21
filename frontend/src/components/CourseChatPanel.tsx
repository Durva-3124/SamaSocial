import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import type { CourseMessage } from "../hooks/useCourse";
import "./CourseChatPanel.css";

interface Props {
  courseId: string | null;
  messages: CourseMessage[];
  streaming: boolean;
  missing: string[];
  error: string | null;
  onSend: (text: string) => void;
  onSyllabusUpload: (file: File, replace: boolean) => void;
}

export default function CourseChatPanel({ courseId, messages, streaming, missing, error, onSend, onSyllabusUpload }: Props) {
  const [input, setInput] = useState("");
  const [confirmReplace, setConfirmReplace] = useState(false);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    setPendingFile(file);
    setConfirmReplace(false);
    onSyllabusUpload(file, false);
  }

  function handleConfirmReplace() {
    if (pendingFile) onSyllabusUpload(pendingFile, true);
    setConfirmReplace(false);
    setPendingFile(null);
  }

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

      {confirmReplace && (
        <div className="ccp-confirm">
          <span>A plan already exists. Replace it?</span>
          <button className="btn btn--primary" onClick={handleConfirmReplace}>Replace</button>
          <button className="btn btn--secondary" onClick={() => { setConfirmReplace(false); setPendingFile(null); }}>Cancel</button>
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

      {/* Syllabus upload slot */}
      <input
        ref={fileRef}
        type="file"
        accept=".pdf"
        style={{ display: "none" }}
        onChange={handleFileChange}
        disabled={!courseId}
      />

      <form className="ccp-form" onSubmit={handleSubmit}>
        <button
          type="button"
          className="btn btn--secondary ccp-attach"
          onClick={() => fileRef.current?.click()}
          disabled={!courseId || streaming}
          title="Upload syllabus PDF"
        >
          📎
        </button>
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
