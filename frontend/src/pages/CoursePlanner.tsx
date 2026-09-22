import { useCallback, useState } from "react";
import { exportCourse } from "../api/courses";
import CourseChatPanel from "../components/CourseChatPanel";
import PlanViewer from "../components/PlanViewer";
import { useCourse } from "../hooks/useCourse";
import "./CoursePlanner.css";

export default function CoursePlanner() {
  const { courseId, intake, missing, plan, planVersion, messages, streaming, error, sendMessage, stop, patch, uploadSyllabusFile, refreshResources } =
    useCourse();
  const [refreshing, setRefreshing] = useState(false);
  const [confirmReplace, setConfirmReplace] = useState(false);
  const [pendingSyllabusFile, setPendingSyllabusFile] = useState<File | null>(null);

  const handleSyllabusUpload = useCallback(
    (file: File, replace: boolean) => {
      uploadSyllabusFile(file, replace).then(() => {
        if (error === "PLAN_EXISTS" && !replace) {
          setPendingSyllabusFile(file);
          setConfirmReplace(true);
        }
      });
    },
    [uploadSyllabusFile, error],
  );

  const handleConfirmReplace = useCallback(() => {
    if (pendingSyllabusFile) uploadSyllabusFile(pendingSyllabusFile, true);
    setConfirmReplace(false);
    setPendingSyllabusFile(null);
  }, [pendingSyllabusFile, uploadSyllabusFile]);

  const handleExport = useCallback(() => {
    if (courseId) exportCourse(courseId);
  }, [courseId]);

  const handleRefresh = useCallback(
    async (lessonId: string | null) => {
      if (!courseId) return;
      setRefreshing(true);
      try {
        await refreshResources(lessonId);
      } finally {
        setRefreshing(false);
      }
    },
    [courseId, refreshResources],
  );

  return (
    <main className="cp-layout">
      <div className="cp-chat">
        <CourseChatPanel
          courseId={courseId}
          messages={messages}
          streaming={streaming}
          missing={missing ?? []}
          error={error === "PLAN_EXISTS" ? null : error}
          onSend={sendMessage}
          onStop={stop}
          onSyllabusUpload={handleSyllabusUpload}
        />
        {confirmReplace && (
          <div className="cp-confirm">
            <span>A plan already exists. Replace it with the uploaded syllabus?</span>
            <button className="btn btn--primary" onClick={handleConfirmReplace}>Replace</button>
            <button className="btn btn--secondary" onClick={() => { setConfirmReplace(false); setPendingSyllabusFile(null); }}>Cancel</button>
          </div>
        )}
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
