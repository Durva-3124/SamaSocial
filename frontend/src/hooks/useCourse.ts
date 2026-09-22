import { useCallback, useEffect, useRef, useState } from "react";
import {
  createCourse,
  getCourse,
  openCourseStream,
  patchPlan,
  refreshResources as apiRefreshResources,
  uploadSyllabus,
  type Course,
  type IntakeData,
} from "../api/courses";
import { SseParser } from "../lib/sse";

export interface CourseMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
}

export interface UseCourseReturn {
  courseId: string | null;
  intake: IntakeData | null;
  missing: string[];
  plan: Course | null;
  planVersion: number;
  messages: CourseMessage[];
  streaming: boolean;
  refreshing: boolean;
  error: string | null;
  sendMessage: (text: string) => Promise<void>;
  stop: () => void;
  patch: (path: string, value: unknown) => Promise<void>;
  uploadSyllabusFile: (file: File, replace: boolean) => Promise<void>;
  refreshResources: (lessonId: string | null) => Promise<boolean>;
}

let _msgCounter = 0;
function nextId() {
  return `cmsg-${++_msgCounter}`;
}

export function useCourse(): UseCourseReturn {
  const [courseId, setCourseId] = useState<string | null>(null);
  const [intake, setIntake] = useState<IntakeData | null>(null);
  const [missing, setMissing] = useState<string[]>([]);
  const [plan, setPlan] = useState<Course | null>(null);
  const [planVersion, setPlanVersion] = useState(0);
  const [messages, setMessages] = useState<CourseMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [refreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cidRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const planVersionRef = useRef(0);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);
  }, []);

  useEffect(() => () => { abortRef.current?.abort(); }, []);

  useEffect(() => {
    createCourse()
      .then((cid) => {
        cidRef.current = cid;
        setCourseId(cid);
        return getCourse(cid);
      })
      .then((state) => {
        setIntake(state.intake);
        setMissing(state.missing);
        setPlan(state.plan);
        planVersionRef.current = state.plan_version;
        setPlanVersion(state.plan_version);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  const sendMessage = useCallback(async (text: string) => {
    const cid = cidRef.current;
    if (!cid) return;

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
      const reader = openCourseStream(cid, text, ctrl.signal);
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
          } else if (event === "intake_state") {
            setIntake(data.intake as IntakeData);
            setMissing(data.missing as string[]);
          } else if (event === "plan_update") {
            const v = data.plan_version as number;
            if (v > planVersionRef.current) {
              planVersionRef.current = v;
              setPlan(data.plan as Course);
              setPlanVersion(v);
            }
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
  }, []);

  const patch = useCallback(async (path: string, value: unknown) => {
    const cid = cidRef.current;
    if (!cid) return;
    try {
      const result = await patchPlan(cid, path, value);
      if (result.plan_version > planVersionRef.current) {
        planVersionRef.current = result.plan_version;
        setPlan(result.plan);
        setPlanVersion(result.plan_version);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Patch failed");
    }
  }, []);

  const uploadSyllabusFile = useCallback(async (file: File, replace: boolean) => {
    const cid = cidRef.current;
    if (!cid) return;
    setError(null);
    setStreaming(true);
    const parser = new SseParser();
    try {
      const reader = await uploadSyllabus(cid, file, replace);
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        for (const { event, data } of parser.push(value)) {
          if (event === "intake_state") {
            setIntake(data.intake as IntakeData);
            setMissing(data.missing as string[]);
          } else if (event === "plan_update") {
            const v = data.plan_version as number;
            if (v > planVersionRef.current) {
              planVersionRef.current = v;
              setPlan(data.plan as Course);
              setPlanVersion(v);
            }
          } else if (event === "token") {
            setMessages((prev) => {
              const last = prev[prev.length - 1];
              if (last?.role === "assistant") {
                return prev.map((m, i) =>
                  i === prev.length - 1
                    ? { ...m, content: m.content + (data.text as string) }
                    : m,
                );
              }
              return [...prev, { id: nextId(), role: "assistant", content: data.text as string }];
            });
          } else if (event === "error") {
            const code = (data as Record<string, string>).code;
            setError(code === "PLAN_EXISTS" ? "PLAN_EXISTS" : (data.message as string));
          }
        }
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Syllabus upload failed");
    } finally {
      setStreaming(false);
    }
  }, []);

  const refreshResources = useCallback(async (lessonId: string | null): Promise<boolean> => {
    const cid = cidRef.current;
    if (!cid) return false;
    const parser = new SseParser();
    try {
      const reader = await apiRefreshResources(cid, lessonId);
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        for (const { event, data } of parser.push(value)) {
          if (event === "plan_update") {
            const v = data.plan_version as number;
            if (v > planVersionRef.current) {
              planVersionRef.current = v;
              setPlan(data.plan as Course);
              setPlanVersion(v);
            }
          }
        }
      }
      return true;
    } catch {
      return false;
    }
  }, []);

  return {
    courseId,
    intake,
    missing,
    plan,
    planVersion,
    messages,
    streaming,
    refreshing,
    error,
    sendMessage,
    stop,
    patch,
    uploadSyllabusFile,
    refreshResources,
  };
}
