import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import NavBar from "./components/NavBar";
import KagePage from "./pages/KagePage";

const LearningAssistant = lazy(() => import("./pages/LearningAssistant"));
const CoursePlanner = lazy(() => import("./pages/CoursePlanner"));

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<KagePage />} />
        <Route
          path="/assistant"
          element={
            <>
              <NavBar />
              <Suspense fallback={<main className="route-loading">Loading workspace...</main>}>
                <LearningAssistant />
              </Suspense>
            </>
          }
        />
        <Route
          path="/planner"
          element={
            <>
              <NavBar />
              <Suspense fallback={<main className="route-loading">Loading planner...</main>}>
                <CoursePlanner />
              </Suspense>
            </>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}
