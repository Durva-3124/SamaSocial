import { Link } from "react-router-dom";
import StudyScene from "../components/StudyScene";
import "./KagePage.css";

export default function KagePage() {
  return (
    <main className="home">
      <section className="home-hero" aria-labelledby="home-heading">
        <div className="home-hero__copy">
          <p className="home-kicker"><span /> A study space built around your sources</p>
          <h1 id="home-heading">Study from<br />what you <em>have.</em></h1>
          <p className="home-hero__sub">
            Bring in lecture notes, slides, videos, or a web page. Ask questions, follow answers back to their sources, and shape a course plan as you go.
          </p>
          <div className="home-hero__actions">
            <Link to="/assistant" className="home-btn home-btn--primary">Open study workspace <span aria-hidden="true">↗</span></Link>
            <Link to="/planner" className="home-btn home-btn--secondary">Plan a course</Link>
          </div>
          <p className="home-hero__note"><span>01</span> Sources in. Better questions out.</p>
        </div>

        <div className="home-hero__art">
          <div className="home-hero__art-head">
            <span>Source map</span>
            <span>PDF <i /> Slides <i /> Video</span>
          </div>
          <StudyScene />
          <div className="home-hero__art-foot"><span>COLLECT</span><span>CONNECT</span><span>UNDERSTAND</span></div>
        </div>
        <div className="home-hero__index" aria-hidden="true">SS / 001</div>
      </section>

      <section className="home-workflow" aria-labelledby="workflow-heading">
        <div className="home-workflow__intro">
          <p className="home-kicker"><span /> From material to momentum</p>
          <h2 id="workflow-heading">Keep the work<br />moving forward.</h2>
        </div>
        <div className="home-workflow__steps">
          <article className="home-step">
            <span className="home-step__number">01</span>
            <div><h3>Ask with context</h3><p>Get answers from the material you added, with references you can check.</p></div>
            <Link to="/assistant" aria-label="Open the learning assistant">↗</Link>
          </article>
          <article className="home-step">
            <span className="home-step__number">02</span>
            <div><h3>Practice what you read</h3><p>Turn your sources into a multiple-choice quiz and see what needs another look.</p></div>
            <Link to="/assistant" aria-label="Create a quiz from your sources">↗</Link>
          </article>
          <article className="home-step">
            <span className="home-step__number">03</span>
            <div><h3>Make a course plan</h3><p>Break a learning goal into editable modules, lessons, and useful resources.</p></div>
            <Link to="/planner" aria-label="Open the course planner">↗</Link>
          </article>
        </div>
      </section>

      <footer className="home-footer">
        <span>Samasocial</span>
        <span>Bring your material. Start anywhere.</span>
        <Link to="/assistant">Go to your workspace <span aria-hidden="true">↗</span></Link>
      </footer>
    </main>
  );
}
