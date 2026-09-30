import { NavLink } from "react-router-dom";
import "./NavBar.css";

export default function NavBar() {
  return (
    <nav className="navbar">
      <span className="navbar-brand">
        <span className="navbar-brand__dot" aria-hidden="true" />
        Samasocial AI
      </span>
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
