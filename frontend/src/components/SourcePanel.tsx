import { useRef, useState } from "react";
import type { SourceRecord } from "../api/sessions";
import "./SourcePanel.css";

interface Props {
  sources: SourceRecord[];
  loading: boolean;
  onAddFile: (file: File) => void;
  onAddUrl: (url: string) => void;
  onRemove: (id: string) => void;
}

const TYPE_ICON: Record<string, string> = {
  pdf: "📄",
  pptx: "📊",
  youtube: "▶️",
  web: "🌐",
};

const STATUS_LABEL: Record<string, string> = {
  processing: "Processing…",
  ready: "Ready",
  failed: "Failed",
};

export default function SourcePanel({ sources, loading, onAddFile, onAddUrl, onRemove }: Props) {
  const [url, setUrl] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) onAddFile(file);
    e.target.value = "";
  }

  function handleUrl(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = url.trim();
    if (trimmed) { onAddUrl(trimmed); setUrl(""); }
  }

  return (
    <aside className="source-panel">
      <h2 className="source-panel__title">Sources</h2>

      <div className="source-panel__actions">
        <button
          className="btn btn--primary"
          onClick={() => fileRef.current?.click()}
          disabled={loading}
        >
          + Upload file
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.pptx"
          style={{ display: "none" }}
          onChange={handleFile}
        />
      </div>

      <form className="source-panel__url-form" onSubmit={handleUrl}>
        <input
          className="source-panel__url-input"
          type="url"
          placeholder="YouTube or webpage URL"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          disabled={loading}
        />
        <button className="btn btn--secondary" type="submit" disabled={loading || !url.trim()}>
          Add
        </button>
      </form>

      <ul className="source-list">
        {sources.length === 0 && (
          <li className="source-list__empty">No sources yet.</li>
        )}
        {sources.map((s) => (
          <li key={s.id} className={`source-item source-item--${s.status}`}>
            <span className="source-item__icon">{TYPE_ICON[s.type] ?? "📁"}</span>
            <div className="source-item__info">
              <span className="source-item__name" title={s.name}>{s.name}</span>
              <span className="source-item__meta">
                {STATUS_LABEL[s.status]}
                {s.status === "ready" && ` · ${s.chunk_count} chunks`}
                {s.status === "failed" && s.error && ` · ${s.error}`}
              </span>
              {s.topics.length > 0 && (
                <div className="source-item__topics">
                  {s.topics.map((t) => <span key={t} className="topic-tag">{t}</span>)}
                </div>
              )}
            </div>
            <button
              className="source-item__remove"
              onClick={() => onRemove(s.id)}
              aria-label={`Remove ${s.name}`}
            >
              ✕
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}
