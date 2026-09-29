import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client";
import SourcePanel from "./SourcePanel";
import { formatSourceActionError } from "../hooks/useSession";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const sources = [
  {
    id: "processing",
    type: "pdf" as const,
    name: "reading.pdf",
    status: "processing" as const,
    error: null,
    chunk_count: 0,
    summary: null,
    topics: [],
    warnings: [],
  },
  {
    id: "ready",
    type: "pptx" as const,
    name: "slides.pptx",
    status: "ready" as const,
    error: null,
    chunk_count: 4,
    summary: null,
    topics: [],
    warnings: ["One image-only slide was skipped."],
  },
  {
    id: "failed",
    type: "web" as const,
    name: "https://example.com",
    status: "failed" as const,
    error: "No readable content was found.",
    chunk_count: 0,
    summary: null,
    topics: [],
    warnings: [],
  },
];

function renderPanel(overrides: Partial<React.ComponentProps<typeof SourcePanel>> = {}) {
  return renderToStaticMarkup(
    <SourcePanel
      sources={[]}
      loading={false}
      uploading={false}
      error={null}
      onAddFile={() => undefined}
      onAddUrl={() => undefined}
      onRemove={() => undefined}
      {...overrides}
    />,
  );
}

// ---------------------------------------------------------------------------
// SourcePanel rendering
// ---------------------------------------------------------------------------

describe("SourcePanel", () => {
  it("renders an empty state when no sources are present", () => {
    const markup = renderPanel();
    expect(markup).toContain("No sources yet.");
  });

  it("renders processing, ready, failed, and warning details", () => {
    const markup = renderPanel({ sources });

    expect(markup).toContain("Processing");
    expect(markup).toContain("Ready");
    expect(markup).toContain("4 chunks");
    expect(markup).toContain("Failed · No readable content was found.");
    expect(markup).toContain("One image-only slide was skipped.");
  });

  it("pluralizes chunk count correctly", () => {
    const singleChunk = [{ ...sources[1], chunk_count: 1 }];
    const markup = renderPanel({ sources: singleChunk });
    expect(markup).toContain("1 chunk");
    expect(markup).not.toContain("1 chunks");

    const multiChunk = [{ ...sources[1], chunk_count: 5 }];
    const markupMulti = renderPanel({ sources: multiChunk });
    expect(markupMulti).toContain("5 chunks");
  });

  it("shows upload progress while a file is being sent", () => {
    const markup = renderPanel({ loading: true, uploading: true });

    expect(markup).toContain("Uploading...");
    // Upload button is disabled
    expect(markup).toContain('disabled=""');
  });

  it("shows URL progress when adding a URL", () => {
    const markup = renderPanel({ loading: true, uploading: false });

    expect(markup).toContain("Adding URL...");
  });

  it("shows an error alert when an error is present", () => {
    const markup = renderPanel({ error: "Unsafe URL: That URL is not allowed." });

    expect(markup).toContain('role="alert"');
    expect(markup).toContain("Unsafe URL: That URL is not allowed.");
  });

  it("renders no error alert when error is null", () => {
    const markup = renderPanel({ error: null });
    expect(markup).not.toContain('role="alert"');
  });

  it("disables the URL form while loading", () => {
    // When loading=true, the URL input and button should be disabled
    const markup = renderPanel({ loading: true });
    // Both input and submit button should have disabled attribute
    const disabledCount = (markup.match(/disabled=""/g) || []).length;
    expect(disabledCount).toBeGreaterThanOrEqual(2);
  });

  it("URL input has an aria-label", () => {
    const markup = renderPanel();
    expect(markup).toContain('aria-label="YouTube or webpage URL"');
  });

  it("icons have aria-hidden", () => {
    const markup = renderPanel({ sources });
    expect(markup).toContain('aria-hidden="true"');
  });

  it("source list has aria-live and aria-label", () => {
    const markup = renderPanel();
    expect(markup).toContain('aria-live="polite"');
    expect(markup).toContain('aria-label="Source ingestion status"');
  });

  it("renders remove button with accessible label", () => {
    const markup = renderPanel({ sources: [sources[0]] });
    expect(markup).toContain('aria-label="Remove reading.pdf"');
  });

  it("renders type icons for all source types", () => {
    const typeSources = [
      { ...sources[0], type: "pdf" as const },
      { ...sources[1], type: "pptx" as const },
      { ...sources[2], type: "youtube" as const, name: "yt" },
      { ...sources[2], id: "w1", type: "web" as const, name: "web" },
    ];
    const markup = renderPanel({ sources: typeSources });
    expect(markup).toContain("📄");
    expect(markup).toContain("📊");
    expect(markup).toContain("▶️");
    expect(markup).toContain("🌐");
  });

  it("renders topics when present", () => {
    const withTopics = [{ ...sources[1], topics: ["Machine Learning", "Python"] }];
    const markup = renderPanel({ sources: withTopics });
    expect(markup).toContain("Machine Learning");
    expect(markup).toContain("Python");
  });

  it("does not render topics section when topics is empty", () => {
    const noTopics = [{ ...sources[0], topics: [] }];
    const markup = renderPanel({ sources: noTopics });
    expect(markup).not.toContain("topic-tag");
  });
});

// ---------------------------------------------------------------------------
// formatSourceActionError
// ---------------------------------------------------------------------------

describe("formatSourceActionError", () => {
  it("labels unsupported files", () => {
    expect(
      formatSourceActionError(
        new ApiError("UNSUPPORTED_FILE", "Only .pdf and .pptx files are supported.", 415),
        "Upload failed",
      ),
    ).toBe("Unsupported file: Only .pdf and .pptx files are supported.");
  });

  it("labels unsafe URLs", () => {
    expect(
      formatSourceActionError(
        new ApiError("UNSAFE_URL", "That URL is not allowed.", 422),
        "Add URL failed",
      ),
    ).toBe("Unsafe URL: That URL is not allowed.");
  });

  it("labels file too large", () => {
    expect(
      formatSourceActionError(
        new ApiError("FILE_TOO_LARGE", "File exceeds the 25 MB limit.", 413),
        "Upload failed",
      ),
    ).toBe("File too large: File exceeds the 25 MB limit.");
  });

  it("labels duplicate source", () => {
    expect(
      formatSourceActionError(
        new ApiError("DUPLICATE_SOURCE", "This file is already being processed.", 409),
        "Upload failed",
      ),
    ).toBe("Already added: This file is already being processed.");
  });

  it("labels too many sources", () => {
    expect(
      formatSourceActionError(
        new ApiError("TOO_MANY_SOURCES", "Sessions are limited to 8 sources.", 400),
        "Upload failed",
      ),
    ).toBe("Too many sources: Sessions are limited to 8 sources.");
  });

  it("returns the error message for unknown ApiError codes", () => {
    expect(
      formatSourceActionError(
        new ApiError("SOME_OTHER_CODE", "Something went wrong.", 500),
        "Upload failed",
      ),
    ).toBe("Something went wrong.");
  });

  it("returns the fallback for unknown ApiError codes with no message", () => {
    expect(
      formatSourceActionError(
        new ApiError("SOME_OTHER_CODE", "", 500),
        "Upload failed",
      ),
    ).toBe("Upload failed");
  });

  it("labels fetch failures as network errors", () => {
    expect(formatSourceActionError(new TypeError("Failed to fetch"), "Upload failed")).toBe(
      "Network error. Check your connection and try again.",
    );
  });

  it("returns error message for generic Error", () => {
    expect(formatSourceActionError(new Error("custom error message"), "Upload failed")).toBe(
      "custom error message",
    );
  });

  it("returns fallback for non-Error unknowns", () => {
    expect(formatSourceActionError("string error", "Upload failed")).toBe("Upload failed");
  });
});
