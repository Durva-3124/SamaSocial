# Samasocial: Extra Features (Mind Map, Flashcards, Glossary, Study Guide Export)

These are **beyond the assignment spec** — not in the graded "Bonus Points" list, so they only pay off if they're cheap and demo well. All four together are about **3.5 to 4 hours**. Build in this order; each is independently cuttable if you run short.

| # | Feature | Effort | Depends on | Cut first if short on time? |
|---|---|---|---|---|
| M18 | Key terms glossary | 30 min | M9 (summaries) | No — cheapest, folds into existing pipeline |
| M19 | Flashcards | 45 min | M9 (quiz chunk sampling) | No — reuses almost everything |
| M20 | Mind map | 1.5 h | M6 (retrieval/chunks), new frontend lib | **Yes, cut first** — most novel code, most that can go wrong |
| M21 | Study guide export | 1 h | M18, M19, M9 | Cut second — nice-to-have, not visually distinctive |

Build M18 before M20/M21 — the glossary and mind map both read better together, and M21 needs M18's output.

---

## Contract additions

Add this block to `docs/API_CONTRACT.md` before building anything, same as M0's contract-first rule.

````markdown
## Task 1 Bonus: Study Tools

| Endpoint | Request | Response |
|---|---|---|
| `GET /sessions/{sid}/sources` | *(extended)* | each source item gains `"glossary": [{"term","definition","locator_text"}]` |
| `POST /sessions/{sid}/mindmap` | `{"source_ids": null\|[..]}` | `200 {"root": MindMapNode}` |
| `POST /sessions/{sid}/flashcards` | `{"num_cards":12,"source_ids":null\|[..]}` | `200 {"cards":[{"id","front","back","source_id","source_name","locator_text"}]}` |
| `GET /sessions/{sid}/study-guide?format=md` | none | `200 text/markdown` attachment |

`MindMapNode`: `{"id","label","summary","source_id":null|str,"locator_text":null|str,"children":[MindMapNode]}` — max depth 3, max 6 children per node.
````

---

## M18: Key Terms Glossary

**Goal:** 4 to 8 term/definition pairs per source, generated alongside the existing summary, shown in the sources panel.
**Depends on:** M9 (`summarizer.py`).
**Files:** `app/services/summarizer.py` (extend), `app/models/session.py` (extend `SourceRecord`), `frontend/src/components/SourceCard.tsx` (extend).

**Amazon Q prompt:**

````text
Read .amazonq/rules/project.md and docs/API_CONTRACT.md. Extend the existing source summary feature to also produce a glossary. Do not create a new endpoint.

1) app/models/session.py: add `GlossaryTerm(BaseModel)`: term:str, definition:str (max ~25 words), locator_text: str | None. Add `glossary: list[GlossaryTerm] = []` to SourceRecord.

2) app/services/summarizer.py:
- Extend the existing `SourceSummary` schema (used by summarize_source) to also include `glossary: list[GlossaryTerm]` (4-8 items). Update the prompt: "Also extract 4 to 8 key terms specific to this content with a short beginner-friendly definition for each, in your own words, not copied verbatim from the source. Skip terms that are common English words." For each term, best-effort match it to the chunk it most likely came from and set locator_text from that chunk's Locator.locator_text(); if no confident match, leave it None.
- Keep the map-reduce path (>12 chunks) working: extract glossary terms per group, then de-duplicate by case-insensitive term text when combining (keep the first definition), cap the final list at 10.
- Store glossary on the SourceRecord alongside summary/topics. GET /sources already returns the full SourceRecord, so no route change is needed — just make sure the serializer includes the new field.

3) Test: FakeLLM scripted with a glossary in its JSON response; assert terms appear on the SourceRecord after summarize_source runs; assert de-duplication across map-reduce groups; assert a source with fewer than 4 usable terms doesn't crash (returns whatever it found, even if under 4).

4) Frontend: in SourceCard.tsx, below the existing summary/topics display, add a collapsible "Key terms" section rendering each glossary term as a small definition list (term in bold, definition below it). Reuse the same collapse pattern already used for the summary. If glossary is empty, don't render the section at all.
````

**Acceptance tests:**
- [ ] `pytest -q tests/test_summarizer.py` passes
- [ ] Load a real source; within the same ~10s window the summary already appears in, 4-8 glossary terms show
- [ ] Terms are genuinely specific to the source (not "the", "data", "system") — spot-check 2 sources
- [ ] A short source (1-2 chunks) still produces a usable glossary, or gracefully produces fewer terms

**Be ready to explain:** why this rides on the existing summarization call instead of a separate LLM round trip (cost, and it's cheap to add).
**Commit:** `feat: key terms glossary alongside source summaries`

---

## M19: Flashcards

**Goal:** A flip-card deck generated from source chunks, separate from the graded quiz mode.
**Depends on:** M9 (`quiz.py`'s chunk-sampling pattern), M7 (source API).
**Files:** `app/services/flashcards.py`, `app/api/flashcards.py`, `frontend/src/components/FlashcardDeck.tsx`, wiring in the Task 1 page.

**Amazon Q prompt:**

````text
Read .amazonq/rules/project.md and docs/API_CONTRACT.md. Implement POST /sessions/{sid}/flashcards.

1) app/services/flashcards.py `async def generate_flashcards(session_id, num_cards, source_ids)`:
- Reuse the same chunk-sampling approach as quiz.py: sample up to `num_cards` chunks spread evenly across the selected (or all ready) sources, preferring chunks with concrete facts/definitions over narrative filler.
- complete_json with schema `FlashcardResponse(cards: list[FlashcardItem])` where FlashcardItem has front (a short question or term, under ~12 words), back (the answer/definition, under ~30 words), chunk_ref (index into the numbered chunks given in the prompt).
- Prompt rule: front must be answerable ONLY from its chunk; back must not just restate the front; no duplicate fronts.
- Server-side validation: drop cards with an out-of-range chunk_ref, an empty front/back, or a front that duplicates another card's front (case-insensitive). Map chunk_ref to source_id/source_name/locator_text. If zero valid cards survive, AppError("FLASHCARDS_FAILED", ..., 502). No ready sources -> AppError("NO_SOURCES", ..., 400).

2) app/api/flashcards.py: route per the contract. num_cards default 12, clamp to 4-24.

3) Test with FakeLLM: malformed card dropped; duplicate front dropped; chunk_ref mapped to correct locator; no sources -> 400; all cards fail validation -> 502.

4) Frontend: FlashcardDeck.tsx, opened from a "Flashcards" button next to the existing "Quiz me" button in Composer.
- One card visible at a time, click or Space to flip (CSS 3D flip transition), Left/Right arrows or buttons to navigate, a small source+locator caption under the back.
- A "shuffle" button and a progress indicator ("Card 4 of 12").
- Track "know it" / "still learning" per card in local component state only (not persisted) with two buttons under the flipped card; show a simple end-of-deck summary ("8 of 12 marked known") and a "Restart" button.
- Keyboard accessible; aria-live announces which side is showing.
````

**Acceptance tests:**
- [ ] `pytest -q tests/test_flashcards.py` passes
- [ ] Generate a real deck; read all cards against the source — fronts are genuinely answerable from their chunk, backs aren't just restating the front
- [ ] No two fronts are duplicates or near-duplicates
- [ ] Deck works end to end in the UI: flip, navigate, shuffle, mark known/learning, restart
- [ ] Mobile 375px: flip animation and buttons remain usable

**Be ready to explain:** why flashcards and the graded quiz share the sampling logic but not the prompt (fronts need to be terse, quiz needs distractors).
**Commit:** `feat: flashcard deck generation and review UI`

---

## M20: Mind Map Generation

**Goal:** A hierarchical topic map per source (or merged across selected sources), rendered as an interactive, clickable tree.
**Depends on:** M6 (chunks/retrieval), M9 (topics, as a fallback seed).
**Files:** `app/services/mindmap.py`, `app/api/mindmap.py`, `frontend/src/components/MindMapView.tsx`, `frontend/package.json` (add `d3-hierarchy`).

**Manual step:** `cd frontend && npm install d3-hierarchy` (small, tree-layout math only — not the whole d3 bundle).

**Amazon Q prompt:**

````text
Read .amazonq/rules/project.md and docs/API_CONTRACT.md. Implement POST /sessions/{sid}/mindmap and a rendering component.

1) app/models/mindmap.py: `MindMapNode(BaseModel)`: id:str, label:str (max ~6 words), summary:str (max ~20 words), source_id: str | None, locator_text: str | None, children: list["MindMapNode"] = []. Use model_rebuild() for the self-reference.

2) app/services/mindmap.py `async def generate_mindmap(session_id, source_ids) -> MindMapNode`:
- Gather chunks from the selected (or all ready) sources. If total chunks > ~40, first summarize in groups (reuse the map-reduce pattern from summarizer.py) to keep the prompt small; otherwise use chunk texts directly, each numbered and tagged with its source.
- complete_json against a schema `MindMapResponse(root: MindMapNode)`. Prompt: build a hierarchical topic map, ROOT is the overall subject (one line), depth of at most 3 levels, at most 6 children per node, each leaf-ish node should reference the chunk number it's grounded in via an internal index field the model returns (add `chunk_ref: int | None` to a raw intermediate schema, map it server-side to source_id/locator_text, then strip chunk_ref before returning — don't expose it in the public MindMapNode).
- Validate: enforce the depth/breadth caps server-side too (truncate extra children rather than erroring, since LLMs sometimes overshoot); assign deterministic ids ("n0", "n0-1", "n0-1-2"...).
- Cache the result on the session (keyed by the sorted tuple of source_ids) so repeat requests for the same source set don't re-call the LLM; invalidate the cache entry when any of those sources is deleted.
- No ready sources -> AppError("NO_SOURCES", ..., 400).

3) app/api/mindmap.py: route per the contract.

4) Test with FakeLLM: depth/breadth caps enforced even if the LLM returns more; chunk_ref correctly mapped and stripped; ids deterministic; cache hit avoids a second LLM call (assert call count via FakeLLM.calls); cache invalidated after a source delete; no sources -> 400.

5) Frontend MindMapView.tsx (uses d3-hierarchy for layout only, plain SVG for rendering — no external CDN, this stays inside the app bundle):
- Fetch the mindmap, build a d3.hierarchy from the root, use d3.tree() for x/y positions, render as an SVG: circles/rounded-rects for nodes with the label, curved paths for links.
- Pan and zoom: wrap in a container with basic pointer-drag panning and +/- zoom buttons (no need for a zoom library — plain CSS transform with a translate/scale state is enough).
- Click a node: show its `summary` and (if present) a "Jump to source" chip with the locator_text, in a small side panel or popover.
- Root node visually distinct (larger, accent color); depth-based color or size falloff.
- Loading skeleton while generating (can take 5-15s for larger sessions); error state with retry.
- Entry point: a "Mind map" button in the sources panel, opening a modal or a dedicated panel; a source-selection checklist if more than one source is loaded (default: all).
````

**Acceptance tests:**
- [ ] `pytest -q tests/test_mindmap.py` passes
- [ ] Generate a real map for a real source; the topic hierarchy makes sense to a human reading the source (spot-check by reading the source yourself)
- [ ] No node exceeds the depth/breadth caps even under adversarial LLM output (test this by scripting FakeLLM to return an oversized tree)
- [ ] Clicking a node with a locator shows a sensible snippet
- [ ] Regenerating for the same source set is fast (cache hit) — regenerating after adding a new source is not (cache miss)
- [ ] Pan/zoom work with mouse and touch; renders correctly at 375px (may need a "view fullscreen" toggle on mobile)

**Be ready to explain:** why the tree is capped server-side (rendering breaks or becomes unreadable with unbounded fan-out), why layout uses d3-hierarchy but not the whole d3 chart library.
**Commit:** `feat: source mind map generation with interactive tree view`

---

## M21: Study Guide Export

**Goal:** One Markdown file per session combining summaries, glossaries, and (if generated) flashcards — downloadable and something a mentor/student could actually use outside the app.
**Depends on:** M18, M19, M9.
**Files:** `app/services/study_guide.py`, `app/api/study_guide.py`, a small frontend "Export study guide" button.

**Amazon Q prompt:**

````text
Read .amazonq/rules/project.md and docs/API_CONTRACT.md. Implement GET /sessions/{sid}/study-guide?format=md.

1) app/services/study_guide.py `def build_study_guide_markdown(session) -> str` (pure function, no LLM call — everything it needs was already generated in M9/M18/M19):
- Title: "# Study Guide: <session created date>" (or a name if sessions gain one later).
- One section per READY source: "## <source name> (<type>)", the summary paragraph, then "### Key terms" as a definition list from glossary, then "### Topics" as a comma-separated line from topics. Skip empty subsections.
- If any flashcards were generated and cached for this session (reuse/extend the mindmap-style cache pattern from M20, or a simple last-generated-deck field on the session), append a final "## Flashcards" section listing each as "**Q:** front  \n**A:** back" pairs.
- Footer: "Generated by Samasocial AI Learning Assistant on <UTC timestamp>."
- Sources with status "failed" or "processing" are skipped with no error.

2) app/api/study_guide.py: route returns `Response(content=markdown, media_type="text/markdown", headers={"Content-Disposition": 'attachment; filename="study-guide.md"'})`. No sources ready -> AppError("NO_SOURCES", ..., 400).

3) Test: session with 2 ready sources (one with glossary, one without) produces correct sections in the right order; a failed source is excluded; a session with no ready sources -> 400; markdown is well-formed (no broken headers).

4) Frontend: add an "Export study guide" button in the sources panel (enabled once at least one source is ready). On click, fetch the endpoint and trigger a browser download using a Blob and a temporary <a> element (same pattern as the Task 2 JSON export in M14, reuse that helper if it already exists as a shared util).
````

**Acceptance tests:**
- [ ] `pytest -q tests/test_study_guide.py` passes
- [ ] Download a guide for a session with 2+ sources; open it in any Markdown viewer — headers, terms and topics render cleanly
- [ ] A source still processing or failed is correctly excluded, no blank section
- [ ] File downloads with the right filename and opens without errors

**Be ready to explain:** why this is pure Markdown assembly (no LLM call) — it's just reusing data you already generated, which keeps this feature nearly free.
**Commit:** `feat: exportable study guide combining summaries, glossary and flashcards`

---

## Quick audit checklist (all four)

Run the universal audit (script + U5–U9) from your existing audit doc after each module, plus:

- [ ] **M18:** glossary terms are genuinely specific to the source, not generic words; de-dup works across map-reduce groups
- [ ] **M19:** no duplicate/near-duplicate flashcard fronts; every front is answerable from its cited chunk; deck works fully offline in the UI (flip/nav/shuffle/mark/restart)
- [ ] **M20 (P1-level check):** adversarial oversized-tree test actually caught by server-side truncation, not just the prompt's request; cache invalidates on source delete; readable at 375px
- [ ] **M21:** excluded sources really are excluded; file is valid Markdown; download works on mobile

## Demo script addition

If you build these, add ~45 seconds to the Task 1 part of your demo video: open the mind map for the loaded sources, click one node, then show the flashcard flip, then trigger the study guide download. Keep it tight — these are extras, and the demo should still spend most of its time on the two graded tasks.
