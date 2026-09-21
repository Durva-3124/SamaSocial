import { BrowserRouter, Route, Routes } from "react-router-dom";
import NavBar from "./components/NavBar";
import LearningAssistant from "./pages/LearningAssistant";
import CoursePlanner from "./pages/CoursePlanner";

export default function App() {
  return (
    <BrowserRouter>
      <NavBar />
      <Routes>
        <Route path="/" element={<LearningAssistant />} />
        <Route path="/planner" element={<CoursePlanner />} />
      </Routes>
    </BrowserRouter>
  );
}
