import { apiFetch } from "./client";

export interface SourceRecord {
  id: string;
  type: "pdf" | "pptx" | "youtube" | "web";
  name: string;
  status: "processing" | "ready" | "failed";
  error: string | null;
  chunk_count: number;
  summary: string | null;
  topics: string[];
}

export interface CitationItem {
  label: string;
  source_id: string;
  source_name: string;
  source_type: string;
  locator: Record<string, unknown>;
  locator_text: string;
  snippet: string;
}

export interface QuizQuestion {
  question: string;
  options: [string, string, string, string];
  answer_index: 0 | 1 | 2 | 3;
  explanation: string;
  source_id: string;
  locator_text: string;
}

export async function createSession(): Promise<string> {
  const data = await apiFetch<{ session_id: string }>("/sessions", { method: "POST" });
  return data.session_id;
}

export async function listSources(sid: string): Promise<SourceRecord[]> {
  const data = await apiFetch<{ sources: SourceRecord[] }>(`/sessions/${sid}/sources`);
  return data.sources;
}

export async function uploadFile(sid: string, file: File): Promise<string> {
  const form = new FormData();
  form.append("file", file);
  const data = await apiFetch<{ source_id: string }>(`/sessions/${sid}/sources/file`, {
    method: "POST",
    headers: {},
    body: form,
  });
  return data.source_id;
}

export async function addUrl(sid: string, url: string): Promise<string> {
  const data = await apiFetch<{ source_id: string }>(`/sessions/${sid}/sources/url`, {
    method: "POST",
    body: JSON.stringify({ url }),
  });
  return data.source_id;
}

export async function deleteSource(sid: string, sourceId: string): Promise<void> {
  await apiFetch(`/sessions/${sid}/sources/${sourceId}`, { method: "DELETE" });
}

export async function fetchQuiz(
  sid: string,
  numQuestions: number,
  sourceIds: string[] | null,
): Promise<QuizQuestion[]> {
  const data = await apiFetch<{ questions: QuizQuestion[] }>(`/sessions/${sid}/quiz`, {
    method: "POST",
    body: JSON.stringify({ num_questions: numQuestions, source_ids: sourceIds }),
  });
  return data.questions;
}

const BASE_URL =
  (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000/api";

export function openChatStream(
  sid: string,
  message: string,
  mode: "normal" | "simple",
): ReadableStreamDefaultReader<Uint8Array> {
  const ctrl = new AbortController();
  const req = fetch(`${BASE_URL}/sessions/${sid}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, mode }),
    signal: ctrl.signal,
  });
  // Return a reader; caller drives consumption
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const res = await req;
      if (!res.ok || !res.body) {
        controller.error(new Error(`Chat request failed: ${res.status}`));
        return;
      }
      const reader = res.body.getReader();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        controller.enqueue(value);
      }
      controller.close();
    },
    cancel() {
      ctrl.abort();
    },
  });
  return stream.getReader();
}
