import { useState } from "react";
import type { QuizQuestion } from "../api/sessions";
import "./QuizModal.css";

interface Props {
  questions: QuizQuestion[];
  onClose: () => void;
}

export default function QuizModal({ questions, onClose }: Props) {
  const [answers, setAnswers] = useState<Record<number, number>>({});
  const [submitted, setSubmitted] = useState(false);

  function pick(qi: number, oi: number) {
    if (!submitted) setAnswers((prev) => ({ ...prev, [qi]: oi }));
  }

  const score = submitted
    ? questions.filter((q, i) => answers[i] === q.answer_index).length
    : 0;

  return (
    <div className="quiz-overlay" role="dialog" aria-modal="true" aria-label="Quiz">
      <div className="quiz-modal">
        <div className="quiz-modal__header">
          <h2 className="quiz-modal__title">Quiz</h2>
          <button className="quiz-modal__close" onClick={onClose} aria-label="Close quiz">✕</button>
        </div>

        {submitted && (
          <p className="quiz-score">
            Score: {score} / {questions.length}
          </p>
        )}

        <ol className="quiz-questions">
          {questions.map((q, qi) => (
            <li key={qi} className="quiz-question">
              <p className="quiz-question__text">{q.question}</p>
              <ul className="quiz-options">
                {q.options.map((opt, oi) => {
                  const chosen = answers[qi] === oi;
                  const correct = submitted && oi === q.answer_index;
                  const wrong = submitted && chosen && oi !== q.answer_index;
                  return (
                    <li
                      key={oi}
                      className={`quiz-option${chosen ? " quiz-option--chosen" : ""}${correct ? " quiz-option--correct" : ""}${wrong ? " quiz-option--wrong" : ""}`}
                      onClick={() => pick(qi, oi)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => e.key === "Enter" && pick(qi, oi)}
                    >
                      {opt}
                    </li>
                  );
                })}
              </ul>
              {submitted && (
                <p className="quiz-explanation">{q.explanation}</p>
              )}
            </li>
          ))}
        </ol>

        <div className="quiz-modal__footer">
          {!submitted ? (
            <button
              className="btn btn--primary"
              onClick={() => setSubmitted(true)}
              disabled={Object.keys(answers).length < questions.length}
            >
              Submit
            </button>
          ) : (
            <button className="btn btn--secondary" onClick={onClose}>Close</button>
          )}
        </div>
      </div>
    </div>
  );
}
