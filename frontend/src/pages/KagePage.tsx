import { Link } from "react-router-dom";
import "./KagePage.css";

export default function KagePage() {
  return (
    <div className="home">

      {/* ── Hero ── */}
      <section className="home-hero">
        <div className="home-hero__bg" aria-hidden="true">
          <div className="home-hero__grid" />
          <div className="home-hero__glow home-hero__glow--blue" />
          <div className="home-hero__glow home-hero__glow--indigo" />
        </div>

        <div className="home-hero__content">
          <div className="home-hero__eyebrow">
            <span className="home-hero__dot" aria-hidden="true" />
            AI-Powered Learning Platform
          </div>

          <h1 className="home-hero__heading">
            Learn anything.<br />
            <span className="home-hero__heading-accent">Understand everything.</span>
          </h1>

          <p className="home-hero__sub">
            Upload your PDFs, slides, videos, and web pages — then chat with them,
            get cited answers, and generate a full course plan. All in one focused workspace.
          </p>

          <div className="home-hero__actions">
            <Link to="/assistant" className="home-btn home-btn--primary">
              <span className="home-btn__icon">📚</span>
              Learning Assistant
            </Link>
            <Link to="/planner" className="home-btn home-btn--secondary">
              <span className="home-btn__icon">🗂️</span>
              Course Planner
            </Link>
          </div>
        </div>

        {/* Feature preview cards */}
        <div className="home-preview" aria-hidden="true">
          <div className="home-preview__card home-preview__card--chat">
            <div className="home-preview__card-header">
              <span className="home-preview__dot home-preview__dot--green" />
              <span className="home-preview__title">Learning Assistant</span>
            </div>
            <div className="home-preview__message home-preview__message--user">
              What is gradient descent?
            </div>
            <div className="home-preview__message home-preview__message--ai">
              Gradient descent is an optimization algorithm that iteratively
              adjusts parameters to minimize a loss function… <span className="home-preview__citation">[S1]</span>
            </div>
          </div>

          <div className="home-preview__card home-preview__card--plan">
            <div className="home-preview__card-header">
              <span className="home-preview__dot home-preview__dot--blue" />
              <span className="home-preview__title">Course Planner</span>
            </div>
            <div className="home-preview__module">
              <span className="home-preview__module-num">1</span>
              <span>Introduction to Machine Learning</span>
            </div>
            <div className="home-preview__module">
              <span className="home-preview__module-num">2</span>
              <span>Supervised Learning Fundamentals</span>
            </div>
            <div className="home-preview__module home-preview__module--dim">
              <span className="home-preview__module-num">3</span>
              <span>Neural Networks & Deep Learning</span>
            </div>
          </div>
        </div>
      </section>

      {/* ── Features ── */}
      <section className="home-features">
        <div className="home-features__grid">

          <div className="home-feature-card">
            <div className="home-feature-card__icon">📄</div>
            <h3 className="home-feature-card__title">Upload Any Source</h3>
            <p className="home-feature-card__desc">
              PDF, PowerPoint, YouTube videos, or any webpage. The AI ingests and indexes everything automatically.
            </p>
          </div>

          <div className="home-feature-card">
            <div className="home-feature-card__icon">💬</div>
            <h3 className="home-feature-card__title">Chat with Citations</h3>
            <p className="home-feature-card__desc">
              Ask questions and get grounded answers with inline source citations. No hallucinations — if it doesn't know, it says so.
            </p>
          </div>

          <div className="home-feature-card">
            <div className="home-feature-card__icon">🧩</div>
            <h3 className="home-feature-card__title">Auto-Generate Quizzes</h3>
            <p className="home-feature-card__desc">
              Turn any set of sources into a multiple-choice quiz instantly. Test your understanding as you study.
            </p>
          </div>

          <div className="home-feature-card">
            <div className="home-feature-card__icon">🗺️</div>
            <h3 className="home-feature-card__title">Structured Course Plans</h3>
            <p className="home-feature-card__desc">
              Describe your learning goal in a conversation. The AI generates a full course with modules, lessons, durations, and resources.
            </p>
          </div>

          <div className="home-feature-card">
            <div className="home-feature-card__icon">✏️</div>
            <h3 className="home-feature-card__title">Inline Editing</h3>
            <p className="home-feature-card__desc">
              Edit course titles, module names, and lesson descriptions directly in the plan. Changes sync instantly.
            </p>
          </div>

          <div className="home-feature-card">
            <div className="home-feature-card__icon">🔗</div>
            <h3 className="home-feature-card__title">Resource Enrichment</h3>
            <p className="home-feature-card__desc">
              Each lesson is enriched with curated YouTube videos and web articles sourced from real APIs — never fabricated.
            </p>
          </div>

        </div>
      </section>

      {/* ── CTA strip ── */}
      <section className="home-cta">
        <h2 className="home-cta__heading">Ready to start learning?</h2>
        <p className="home-cta__sub">Pick a tool and get started in seconds. No sign-up required.</p>
        <div className="home-cta__actions">
          <Link to="/assistant" className="home-btn home-btn--primary home-btn--lg">
            Open Learning Assistant →
          </Link>
          <Link to="/planner" className="home-btn home-btn--ghost home-btn--lg">
            Build a Course Plan →
          </Link>
        </div>
      </section>

    </div>
  );
}
