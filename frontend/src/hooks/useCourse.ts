import { useCallback, useEffect, useRef, useState } from "react";
import {
  createCourse,
  getCourse,
  openCourseStream,
  patchPlan,
  uploadSyllabus,
  type Course,
  type IntakeData,
} from "../api/courses";

export interface CourseMessage {
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
  patch: (path: string, value: unknown) => Promise<void>;
  uploadSyllabusFile: (file: File, replace: boolean) => Promise<void>;
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
        setPlanVersion(state.plan_version);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  const sendMessage = useCallback(async (text: string) => {
    const cid = cidRef.current;
    if (!cid) return;
    setError(null);
    setMessages((prev) => [...prev, { role: "user", content: text }]);

    const assistantIdx = messages.length + 1;
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);
    setStreaming(true);

    const decoder = new TextDecoder();
    let buffer = "";
    let fullContent = "";

    try {
      const reader = openCourseStream(cid, text);
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
          const data = JSON.parse(dataLine.slice(6)) as Record<string, unknown>;

          if (event === "token") {
            fullContent += data.text as string;
            setMessages((prev) => {
              const next = [...prev];
              next[assistantIdx] = { ...next[assistantIdx], content: fullContent };
              return next;
            });
          } else if (event === "intake_state") {
            setIntake(data.intake as IntakeData);
            setMissing(data.missing as string[]);
          } else if (event === "plan_update") {
            setPlan(data.plan as Course);
            setPlanVersion(data.plan_version as number);
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
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages.length]);

  const patch = useCallback(async (path: string, value: unknown) => {
    const cid = cidRef.current;
    if (!cid) return;
    try {
      const result = await patchPlan(cid, path, value);
      setPlan(result.plan);
      setPlanVersion(result.plan_version);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Patch failed");
    }
  }, []);

  const uploadSyllabusFile = useCallback(async (file: File, replace: boolean) => {
    const cid = cidRef.current;
    if (!cid) return;
    setError(null);
    setStreaming(true);
    const decoder = new TextDecoder();
    let buffer = "";
    try {
      const reader = await uploadSyllabus(cid, file, replace);
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
          const data = JSON.parse(dataLine.slice(6)) as Record<string, unknown>;
          if (event === "intake_state") {
            setIntake(data.intake as IntakeData);
            setMissing(data.missing as string[]);
          } else if (event === "plan_update") {
            setPlan(data.plan as Course);
            setPlanVersion(data.plan_version as number);
          } else if (event === "token") {
            // append to last assistant message or create one
            setMessages((prev) => {
              const last = prev[prev.length - 1];
              if (last?.role === "assistant") {
                const next = [...prev];
                next[next.length - 1] = { ...last, content: last.content + (data.text as string) };
                return next;
              }
              return [...prev, { role: "assistant", content: data.text as string }];
            });
          } else if (event === "error") {
            const code = (data as Record<string, string>).code;
            if (code === "PLAN_EXISTS") {
              // bubble up so CoursePlanner can show confirm dialog
              setError("PLAN_EXISTS");
            } else {
              setError(data.message as string);
            }
          }
        }
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Syllabus upload failed");
    } finally {
      setStreaming(false);
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
    patch,
    uploadSyllabusFile,
  };
}
