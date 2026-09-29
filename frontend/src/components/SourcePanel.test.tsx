import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client";
import SourcePanel from "./SourcePanel";
import { formatSourceActionError } from "../hooks/useSession";

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

describe("SourcePanel", () => {
  it("renders processing, ready, failed, and warning details", () => {
    const markup = renderPanel({ sources });

    expect(markup).toContain("Processing");
    expect(markup).toContain("Ready · 4 chunks");
    expect(markup).toContain("Failed · No readable content was found.");
    expect(markup).toContain("One image-only slide was skipped.");
  });

  it("shows upload progress while a file is being sent", () => {
    const markup = renderPanel({ loading: true, uploading: true });

    expect(markup).toContain("Uploading...");
    expect(markup).toContain('button class="btn btn--primary" disabled=""');
  });

  it("shows URL progress and an actionable source error", () => {
    const markup = renderPanel({ loading: true, error: "Unsafe URL: That URL is not allowed." });

    expect(markup).toContain("Adding URL...");
    expect(markup).toContain('role="alert"');
    expect(markup).toContain("Unsafe URL: That URL is not allowed.");
  });
});

describe("formatSourceActionError", () => {
  it("labels unsupported files and unsafe URLs", () => {
    expect(formatSourceActionError(
      new ApiError("UNSUPPORTED_FILE", "Only .pdf and .pptx files are supported.", 415),
      "Upload failed",
    )).toBe("Unsupported file: Only .pdf and .pptx files are supported.");

    expect(formatSourceActionError(
      new ApiError("UNSAFE_URL", "That URL is not allowed.", 422),
      "Add URL failed",
    )).toBe("Unsafe URL: That URL is not allowed.");
  });

  it("labels fetch failures as network errors", () => {
    expect(formatSourceActionError(new TypeError("Failed to fetch"), "Upload failed"))
      .toBe("Network error. Check your connection and try again.");
  });
});