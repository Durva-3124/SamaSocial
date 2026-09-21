import { useCallback, useState } from "react";
import { exportCourse, refreshResources } from "../api/courses";
import CourseChatPanel from "../components/CourseChatPanel";
import PlanViewer from "../components/PlanViewer";
import { useCourse } from "../hooks/useCourse";
import "./CoursePlanner.css";

export default function CoursePlanner() {
  const { courseId, intake, missing, plan, planVersion, messages, streaming, error, sendMessage, patch } =
    useCourse();
  const [refreshing, setRefreshing] = useState(false);

  const handleExport = useCallback(() => {
    if (courseId) exportCourse(courseId);
  }, [courseId]);

  const handleRefresh = useCallback(
    async (lessonId: string | null) => {
      if (!courseId) return;
      setRefreshing(true);
      try {
        const reader = await refreshResources(courseId, lessonId);
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          // plan_update events are handled server-side; we just drain the stream
        }
      } catch {
        // silent — plan already updated via SSE if partial
      } finally {
        setRefreshing(false);
      }
    },
    [courseId],
  );

  return (
    <main className="cp-layout">
      <div className="cp-chat">
        <CourseChatPanel
          messages={messages}
          streaming={streaming}
          missing={missing ?? []}
          error={error}
          onSend={sendMessage}
        />
      </div>

      <div className="cp-plan">
        {plan ? (
          <PlanViewer
            plan={plan}
            planVersion={planVersion}
            onPatch={patch}
            onExport={handleExport}
            onRefresh={handleRefresh}
            refreshing={refreshing}
          />
        ) : (
          <div className="cp-empty">
            <p>Your course plan will appear here once the AI has enough information.</p>
            {intake?.topic && (
              <p className="cp-intake-hint">
                Topic: <strong>{intake.topic}</strong>
              </p>
            )}
          </div>
        )}
      </div>
    </main>
  );
}
