import { KageLandingPage } from "../shaders/KageLandingPage";
import { Link } from "react-router-dom";
import "./KagePage.css";

export default function KagePage() {
  return (
    <div className="shader-frame">
      <nav className="app-dock" aria-label="Samasocial workspace">
        <Link className="app-dock__brand" to="/" aria-label="Samasocial home">
          <span className="app-dock__mark">S</span>
          <span>Samasocial</span>
        </Link>
        <div className="app-dock__links">
          <Link to="/assistant">Learning Assistant</Link>
          <Link to="/planner">Course Planner</Link>
        </div>
      </nav>
      <KageLandingPage
        headingFont="onest"
        bodyFont="onest"
        headingWeight="400"
        bodyWeight="300"
        primaryColor="#e0231c"
        headingSize={46}
        bodySize={17}
        headingLetterSpacing={-0.012}
      />
    </div>
  );
}