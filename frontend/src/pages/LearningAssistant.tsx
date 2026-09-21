import { useState } from "react";
import { fetchQuiz, type QuizQuestion } from "../api/sessions";
import ChatPanel from "../components/ChatPanel";
import QuizModal from "../components/QuizModal";
import SourcePanel from "../components/SourcePanel";
import { useChat } from "../hooks/useChat";
import { useSession } from "../hooks/useSession";
import "./LearningAssistant.css";

export default function LearningAssistant() {
  const { sessionId, sources, loading, error, addFile, addUrlSource, removeSource } = useSession();
  const { messages, streaming, error: chatError, sendMessage } = useChat();
  const [quizQuestions, setQuizQuestions] = useState<QuizQuestion[] | null>(null);
  const [quizLoading, setQuizLoading] = useState(false);
  const [quizError, setQuizError] = useState<string | null>(null);

  const readySources = sources.filter((s) => s.status === "ready");
  const hasReady = readySources.length > 0;

  async function handleQuiz() {
    if (!sessionId || !hasReady) return;
    setQuizLoading(true);
    setQuizError(null);
    try {
      const qs = await fetchQuiz(sessionId, 5, null);
      setQuizQuestions(qs);
    } catch (e: unknown) {
      setQuizError(e instanceof Error ? e.message : "Quiz failed");
    } finally {
      setQuizLoading(false);
    }
  }

  function handleSend(text: string, mode: "normal" | "simple") {
    if (sessionId) sendMessage(sessionId, text, mode);
  }

  return (
    <main className="la-layout">
      <div className="la-sidebar">
        <SourcePanel
          sources={sources}
          loading={loading}
          onAddFile={addFile}
          onAddUrl={addUrlSource}
          onRemove={removeSource}
        />
        {error && <p className="la-error">{error}</p>}
        <div className="la-quiz-bar">
          <button
            className="btn btn--secondary la-quiz-btn"
            onClick={handleQuiz}
            disabled={!hasReady || quizLoading}
          >
            {quizLoading ? "Generating…" : "Take Quiz"}
          </button>
          {quizError && <p className="la-error">{quizError}</p>}
        </div>
      </div>

      <div className="la-chat">
        <ChatPanel
          messages={messages}
          streaming={streaming}
          error={chatError}
          disabled={!hasReady}
          onSend={handleSend}
        />
      </div>

      {quizQuestions && (
        <QuizModal questions={quizQuestions} onClose={() => setQuizQuestions(null)} />
      )}
    </main>
  );
}
