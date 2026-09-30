import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import NavBar from "./components/NavBar";
import KagePage from "./pages/KagePage";
import "./App.css";

const LearningAssistant = lazy(() => import("./pages/LearningAssistant"));
const CoursePlanner = lazy(() => import("./pages/CoursePlanner"));

export default function App() {
  return (
    <BrowserRouter>
      {/* NavBar appears on every route — consistent UI across the whole app */}
      <NavBar />
      <Routes>
        <Route path="/" element={<KagePage />} />
        <Route
          path="/assistant"
          element={
            <Suspense fallback={<main className="route-loading">Loading workspace…</main>}>
              <LearningAssistant />
            </Suspense>
          }
        />
        <Route
          path="/planner"
          element={
            <Suspense fallback={<main className="route-loading">Loading planner…</main>}>
              <CoursePlanner />
            </Suspense>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}
