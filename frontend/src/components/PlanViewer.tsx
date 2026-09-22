import { useState } from "react";
import type { Course, Module, Lesson } from "../api/courses";
import "./PlanViewer.css";

interface Props {
  plan: Course;
  planVersion: number;
  onPatch: (path: string, value: unknown) => void;
  onExport: () => void;
  onRefresh: (lessonId: string | null) => void;
  refreshing: boolean;
}

interface EditableTextProps {
  value: string;
  onCommit: (v: string) => void;
  className?: string;
  multiline?: boolean;
}

function EditableText({ value, onCommit, className, multiline }: EditableTextProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);

  function commit() {
    setEditing(false);
    if (draft.trim() && draft !== value) onCommit(draft.trim());
    else setDraft(value);
  }

  if (!editing) {
    return (
      <span
        className={`editable ${className ?? ""}`}
        onClick={() => { setDraft(value); setEditing(true); }}
        title="Click to edit"
      >
        {value}
      </span>
    );
  }

  if (multiline) {
    return (
      <textarea
        className={`editable editable--active ${className ?? ""}`}
        value={draft}
        autoFocus
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => { if (e.key === "Escape") { setEditing(false); setDraft(value); } }}
      />
    );
  }

  return (
    <input
      className={`editable editable--active ${className ?? ""}`}
      value={draft}
      autoFocus
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") commit();
        if (e.key === "Escape") { setEditing(false); setDraft(value); }
      }}
    />
  );
}

function isHttpUrl(url: string): boolean {
  try {
    const { protocol } = new URL(url);
    return protocol === "http:" || protocol === "https:";
  } catch {
    return false;
  }
}

interface LessonRowProps {
  lesson: Lesson;
  modIdx: number;
  lesIdx: number;
  onPatch: (path: string, value: unknown) => void;
  onRefresh: (lessonId: string | null) => void;
}

function LessonRow({ lesson, modIdx, lesIdx, onPatch, onRefresh }: LessonRowProps) {
  const [open, setOpen] = useState(false);
  const base = `/modules/${modIdx}/lessons/${lesIdx}`;

  return (
    <li className="pv-lesson">
      <div className="pv-lesson-header">
        <button className="pv-toggle" onClick={() => setOpen((o) => !o)}>
          {open ? "▾" : "▸"}
        </button>
        <EditableText
          value={lesson.title}
          onCommit={(v) => onPatch(`${base}/title`, v)}
          className="pv-lesson-title"
        />
        <span className="pv-duration">{lesson.duration_minutes}m</span>
        <button
          className="btn btn--ghost pv-refresh-btn"
          onClick={() => onRefresh(lesson.id)}
          title="Refresh resources"
        >
          ↻
        </button>
      </div>

      {open && lesson.resources.length > 0 && (
        <ul className="pv-resources">
          {lesson.resources.map((r) => (
            <li key={r.id} className="pv-resource">
              <span className={`pv-resource-type pv-resource-type--${r.type}`}>{r.type}</span>
              {isHttpUrl(r.url) ? (
                <a
                  href={r.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="pv-resource-link"
                >
                  {r.title}
                </a>
              ) : (
                <span className="pv-resource-link">{r.title}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

interface ModuleCardProps {
  mod: Module;
  modIdx: number;
  onPatch: (path: string, value: unknown) => void;
  onRefresh: (lessonId: string | null) => void;
}

function ModuleCard({ mod, modIdx, onPatch, onRefresh }: ModuleCardProps) {
  const [open, setOpen] = useState(true);

  return (
    <div className="pv-module">
      <div className="pv-module-header">
        <button className="pv-toggle" onClick={() => setOpen((o) => !o)}>
          {open ? "▾" : "▸"}
        </button>
        <EditableText
          value={mod.title}
          onCommit={(v) => onPatch(`/modules/${modIdx}/title`, v)}
          className="pv-module-title"
        />
      </div>
      {open && (
        <ul className="pv-lessons">
          {mod.lessons.map((les, li) => (
            <LessonRow
              key={les.id}
              lesson={les}
              modIdx={modIdx}
              lesIdx={li}
              onPatch={onPatch}
              onRefresh={onRefresh}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

export default function PlanViewer({ plan, planVersion, onPatch, onExport, onRefresh, refreshing }: Props) {
  return (
    <section className="pv">
      <div className="pv-header">
        <div className="pv-title-row">
          <EditableText
            value={plan.title}
            onCommit={(v) => onPatch("/title", v)}
            className="pv-course-title"
          />
          <span className="pv-version">v{planVersion}</span>
        </div>
        <EditableText
          value={plan.description}
          onCommit={(v) => onPatch("/description", v)}
          className="pv-course-desc"
          multiline
        />
        <div className="pv-meta">
          <span>{plan.total_weeks} weeks</span>
          <span>·</span>
          <span>{plan.modules.length} modules</span>
        </div>
        <div className="pv-actions">
          <button
            className="btn btn--secondary"
            onClick={() => onRefresh(null)}
            disabled={refreshing}
          >
            {refreshing ? "Refreshing…" : "↻ Resources"}
          </button>
          <button className="btn btn--primary" onClick={onExport}>
            Export JSON
          </button>
        </div>
      </div>

      <div className="pv-modules">
        {plan.modules.map((mod, mi) => (
          <ModuleCard
            key={mod.id}
            mod={mod}
            modIdx={mi}
            onPatch={onPatch}
            onRefresh={onRefresh}
          />
        ))}
      </div>
    </section>
  );
}
