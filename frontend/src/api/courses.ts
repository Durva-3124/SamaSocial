import { apiFetch, BASE_URL } from "./client";

export type DifficultyLevel = "beginner" | "intermediate" | "advanced";

export interface Audience {
  age_group: string;
  level: DifficultyLevel;
  prior_knowledge: string;
}

export interface Duration {
  weeks: number;
  sessions_per_week: number;
  session_minutes: number;
}

export interface Resource {
  id: string;
  title: string;
  url: string;
  type: "video" | "article" | "exercise" | "other";
  validated: boolean;
}

export interface Lesson {
  id: string;
  title: string;
  duration_minutes: number;
  difficulty: DifficultyLevel;
  objectives: string[];
  topics: string[];
  resources: Resource[];
}

export interface Module {
  id: string;
  title: string;
  difficulty: DifficultyLevel;
  prerequisites: string[];
  lessons: Lesson[];
}

export interface Course {
  title: string;
  description: string;
  level: DifficultyLevel;
  total_weeks: number;
  goals: string[];
  audience: Audience | null;
  duration: Duration | null;
  modules: Module[];
}

export interface IntakeData {
  topic: string | null;
  level: DifficultyLevel | null;
  duration_weeks: number | null;
  sessions_per_week: number | null;
  age_group: string | null;
  prior_knowledge: string | null;
  goals: string[];
  prerequisites: string[];
  extra: Record<string, unknown>;
}

export interface CourseState {
  intake: IntakeData;
  missing: string[];
  plan: Course | null;
  plan_version: number;
  messages: { role: string; content: string }[];
}

export async function createCourse(): Promise<string> {
  const data = await apiFetch<{ course_id: string }>("/courses", { method: "POST" });
  return data.course_id;
}

export async function getCourse(cid: string): Promise<CourseState> {
  return apiFetch<CourseState>(`/courses/${cid}`);
}

export async function patchPlan(
  cid: string,
  path: string,
  value: unknown,
): Promise<{ plan: Course; plan_version: number }> {
  return apiFetch(`/courses/${cid}/plan`, {
    method: "PATCH",
    body: JSON.stringify({ path, value }),
  });
}

export async function exportCourse(cid: string): Promise<void> {
  const a = document.createElement("a");
  a.href = `${BASE_URL}/courses/${cid}/export`;
  a.download = "course.json";
  a.click();
}

export async function uploadSyllabus(
  cid: string,
  file: File,
  replace = false,
): Promise<ReadableStreamDefaultReader<Uint8Array>> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(
    `${BASE_URL}/courses/${cid}/syllabus${replace ? "?replace=true" : ""}`,
    { method: "POST", body: form },
  );
  if (!res.ok || !res.body) throw new Error(`Syllabus upload failed: ${res.status}`);
  return res.body.getReader();
}

export async function refreshResources(
  cid: string,
  lessonId: string | null,
): Promise<ReadableStreamDefaultReader<Uint8Array>> {
  const res = await fetch(`${BASE_URL}/courses/${cid}/resources/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lesson_id: lessonId }),
  });
  if (!res.ok || !res.body) throw new Error("Refresh failed");
  return res.body.getReader();
}

export function openCourseStream(
  cid: string,
  message: string,
  signal: AbortSignal,
): ReadableStreamDefaultReader<Uint8Array> {
  const req = fetch(`${BASE_URL}/courses/${cid}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
    signal,
  });
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const res = await req;
      if (!res.ok || !res.body) {
        controller.error(new Error(`Chat failed: ${res.status}`));
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
  });
  return stream.getReader();
}
