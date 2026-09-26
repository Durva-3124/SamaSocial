# Samasocial Frontend Guide

The frontend is a React 19 + TypeScript + Vite application. It provides the Samasocial landing experience, a source-grounded Learning Assistant, and an AI Course Planner.

## Quick Start

```powershell
cd frontend
npm install
npm run dev
```

The development command starts the Vite frontend and the local backend together. The frontend is normally available at `http://localhost:5173`.

Available commands:

| Command | Purpose |
|---|---|
| `npm run dev` | Start frontend and backend development processes |
| `npm run dev:frontend` | Start only the Vite frontend |
| `npm run dev:backend` | Start only the backend helper process |
| `npm run build` | Run TypeScript validation and create a production build |
| `npm run preview` | Serve the production build locally |
| `npm run lint` | Run Oxlint |
| `npm run test` | Run frontend Vitest tests |

The frontend API base URL defaults to `http://localhost:8000/api`. Set `VITE_API_URL` when the backend is hosted elsewhere:

```powershell
$env:VITE_API_URL = "http://localhost:8000/api"
```

## Routes

| Route | Page | Purpose |
|---|---|---|
| `/` | Samasocial landing page | Explains the learning workspace and links directly to the two working tools |
| `/assistant` | Learning Assistant | Upload sources, ask grounded questions, and generate quizzes |
| `/planner` | Course Planner | Describe a learning goal, generate a course, edit it, and export it |

The landing page and application routes use React Router. The Learning Assistant and Course Planner are lazy-loaded so their larger feature code is not included in the first landing-page interaction.

## Landing Page

The root route is implemented by `KagePage` and `KageLandingPage`. The page keeps the authored Three.js world, scroll scenes, responsive layout, navigation, and animated sections, but its visible copy is Samasocial-specific.

### Landing elements

- Samasocial brand dock with links to Learning Assistant and Course Planner.
- Hero statement focused on turning notes and links into clearer learning.
- Primary action: `Open Learning Assistant`.
- Secondary action: `Build a Course Plan`.
- Four learning pillars:
  - Bring your sources.
  - Ask with context.
  - Build your course.
  - Check your progress.
- Source, conversation, review, and planning image cards.
- Source-grounded learning explanation section.
- Course planning workflow section.
- Progress and return-to-learning CTA section.
- Footer links to the major learning workflows.
- Scroll chapter rail and section navigation.
- Responsive mobile navigation and reduced-motion support.

### Landing interactions

- Scroll changes the camera scene and active chapter.
- Section links use smooth scrolling.
- Card hover states animate the live scene/card treatment.
- The mobile menu opens and closes from the burger control.
- Hero actions navigate to the real React application routes.
- The page uses local same-origin study images so the WebGL cloth effect is not blocked by browser canvas security rules.

### Landing performance

The page contains a live WebGL renderer, post-processing, foreground layers, and card viewports. Chrome scrolling is optimized by:

- Passive scroll listeners.
- Skipping static card redraws while scrolling.
- Rendering the expensive WebGL presentation at a lighter cadence during active scrolling.
- Restoring full rendering shortly after scrolling stops.
- Lazy-loading the Learning Assistant and Course Planner route bundles.

## Learning Assistant

The Learning Assistant is implemented by `src/pages/LearningAssistant.tsx`.

### Source workspace

The source panel supports:

- Uploading supported files such as PDF and PPTX files.
- Adding web URLs.
- Adding YouTube URLs through the backend ingestion flow.
- Viewing source processing state.
- Seeing source errors.
- Removing sources.
- Waiting for sources to become ready before chatting.

Source statuses include processing, ready, and failed. Chat and quiz controls remain disabled until at least one source is ready.

### Grounded chat

The chat panel supports:

- Normal answer mode.
- Simple explanation mode.
- Streaming assistant responses through SSE.
- Stop/cancel for an active response.
- Markdown rendering in assistant messages.
- Citation labels and source names.
- Citation locator text such as page, slide, or transcript location.
- A declined-answer state when the available sources do not contain enough information.
- Automatic scrolling to the newest message.

The frontend blocks empty messages and prevents a second send while a response is streaming.

### Quiz workflow

The `Take Quiz` control requests five multiple-choice questions from the current session.

The quiz modal supports:

- Four answer choices per question.
- Keyboard selection with Enter.
- Answer locking after submission.
- Correct and incorrect answer styling.
- Score display.
- Explanations after submission.
- Closing and returning to the source/chat workspace.

## Course Planner

The Course Planner is implemented by `src/pages/CoursePlanner.tsx`.

### Course intake chat

The course chat accepts natural-language planning information such as:

- Topic.
- Learning goal.
- Current level.
- Prior knowledge.
- Timeline.
- Sessions per week.
- Audience or age group.
- Prerequisites.

The planner reports missing intake fields while the conversation is incomplete. Responses stream through SSE, and the UI supports stopping an active response.

### Syllabus upload

The planner supports uploading a syllabus PDF. The upload can:

- Extract intake information.
- Update the missing-information state.
- Generate or update a course plan.
- Stream progress and assistant feedback.
- Ask for confirmation before replacing an existing plan.

### Plan viewer

Once enough information is available, the plan viewer displays the generated course. It supports:

- Course title and description.
- Level, duration, goals, and audience information.
- Modules and lessons.
- Lesson objectives, topics, and resources.
- Inline editing through JSON-pointer based plan patches.
- Plan version tracking.
- Refreshing resources for the complete course or a selected lesson.
- Exporting the course as a JSON download.
- Loading and empty states when no plan exists yet.

Resource links are only rendered as links for HTTP and HTTPS URLs. Unsafe or unsupported protocols are displayed as plain text.

## Frontend Architecture

```text
src/
  App.tsx                    Router and route-level lazy loading
  main.tsx                   React root and global styles
  pages/
    KagePage.tsx             Landing page shell and application dock
    LearningAssistant.tsx    Source chat and quiz workflow
    CoursePlanner.tsx        Course intake and plan workflow
  components/
    NavBar.tsx               Assistant/planner navigation
    SourcePanel.tsx          Source upload and source list
    ChatPanel.tsx            Grounded chat UI
    QuizModal.tsx            Quiz interaction
    CourseChatPanel.tsx      Course intake conversation
    PlanViewer.tsx           Course plan display and editing
  hooks/
    useSession.ts            Learning Assistant session and source state
    useChat.ts               Learning Assistant SSE chat state
    useCourse.ts             Course creation, chat, plan, and resource state
  api/
    client.ts                Shared API base URL and JSON error handling
    sessions.ts              Session, source, chat, and quiz requests
    courses.ts               Course, syllabus, plan, export, and resource requests
  lib/
    sse.ts                   Streaming event parser
  shaders/
    KageLandingPage.tsx      Samasocial landing component wrapper
    landing-pages/           Landing frame, typography, recipe, and source bundle
```

## Backend Dependency

The frontend requires the FastAPI backend for all AI functionality. The landing page can render independently, but these operations require the backend:

- Creating a learning session.
- Ingesting files, web pages, and YouTube sources.
- Chat streaming.
- Quiz generation.
- Creating and loading courses.
- Course planning chat.
- Syllabus processing.
- Plan patching and export.
- Resource refresh.

The backend uses SSE for streaming responses. A healthy local backend should respond at:

```text
GET http://localhost:8000/api/health
```

## State and Error Behavior

- Session and course state is held by frontend hooks while the page is mounted.
- Active streams use `AbortController` for stop/unmount cleanup.
- API errors are surfaced in the relevant page or panel.
- A missing source prevents Learning Assistant chat and quiz submission.
- A missing course prevents syllabus upload until course creation completes.
- Existing course replacement requires explicit confirmation.
- Empty course plans show an instructional placeholder and the detected topic when available.

## Styling and Accessibility

Global styling is in `src/index.css` and `src/styles/tokens.css`. Feature styles live beside their pages and components.

The interface includes:

- Keyboard-focus styles.
- Semantic navigation and form controls.
- Accessible labels for source removal and modal closing.
- `aria-live="polite"` message regions for streamed chat.
- Keyboard-operable quiz options.
- Reduced-motion handling in the landing document.
- Responsive layouts for desktop and mobile widths.

## Known Limitations

- The backend stores sessions and courses in memory, so data is lost after a backend restart.
- A single backend worker should be used with the in-memory stores.
- The embedding model has a first-run download/cold-start cost.
- Resource refresh can be slow because URLs are validated before use.
- No authentication layer is currently implemented.
- YouTube sources require usable captions.
- The quality of cross-source retrieval depends on embeddings and chunk overlap.
- Real LLM and embedding evaluation requires configured API credentials.

See [`docs/API_CONTRACT.md`](../docs/API_CONTRACT.md) for request and response details, and [`docs/LIMITATIONS.md`](../docs/LIMITATIONS.md) for backend limitations.
