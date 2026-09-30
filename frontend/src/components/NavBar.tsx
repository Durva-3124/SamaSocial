import { NavLink } from "react-router-dom";
import "./NavBar.css";

export default function NavBar() {
  return (
    <nav className="navbar">
      {/* Brand links back to home */}
      <NavLink to="/" className="navbar-brand" aria-label="Samasocial home">
        <span className="navbar-brand__dot" aria-hidden="true" />
        Samasocial AI
      </NavLink>

      <div className="navbar-links">
        <NavLink to="/assistant" className={({ isActive }) => (isActive ? "active" : "")}>
          Learning Assistant
        </NavLink>
        <NavLink to="/planner" className={({ isActive }) => (isActive ? "active" : "")}>
          Course Planner
        </NavLink>
      </div>
    </nav>
  );
}
