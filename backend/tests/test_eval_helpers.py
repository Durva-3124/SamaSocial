"""Offline tests for eval/scoring.py pure helper functions."""
import pytest
from eval.scoring import (
    citation_correct,
    injection_resisted,
    is_declined,
    keyword_match,
    retrieval_hit,
    score_summary,
)


# ── keyword_match ─────────────────────────────────────────────────────────────

def test_keyword_match_all_present():
    assert keyword_match("Photosynthesis converts light into glucose and chemical energy.", ["glucose", "chemical energy"])

def test_keyword_match_case_insensitive():
    assert keyword_match("The Calvin Cycle occurs in the Stroma.", ["calvin cycle", "STROMA"])

def test_keyword_match_missing_one():
    assert not keyword_match("Photosynthesis produces oxygen.", ["glucose", "oxygen"])

def test_keyword_match_empty_keywords():
    assert keyword_match("anything", [])

def test_keyword_match_empty_answer():
    assert not keyword_match("", ["glucose"])


# ── citation_correct ──────────────────────────────────────────────────────────

def test_citation_correct_match():
    citations = [{"locator_text": "page 3"}, {"locator_text": "slide 2"}]
    assert citation_correct(citations, ["page 3"])

def test_citation_correct_partial_match():
    # Exact normalised match: "page 3" must NOT match "page 3 of the document"
    citations = [{"locator_text": "page 3 of the document"}]
    assert citation_correct(citations, ["page 3"]) is False

def test_citation_correct_exact_match_true():
    # Exact match: locator_text equals the expected string
    citations = [{"locator_text": "page 3"}]
    assert citation_correct(citations, ["page 3"]) is True

def test_citation_correct_no_match():
    citations = [{"locator_text": "slide 5"}]
    assert not citation_correct(citations, ["page 3"])

def test_citation_correct_no_expectation():
    assert citation_correct([], []) is None

def test_citation_correct_empty_citations_with_expectation():
    assert not citation_correct([], ["page 1"])


# ── retrieval_hit ─────────────────────────────────────────────────────────────

def test_retrieval_hit_found():
    chunks = [{"text": "RuBisCO fixes CO2 in carbon fixation."}]
    assert retrieval_hit(chunks, ["RuBisCO", "CO2"])

def test_retrieval_hit_not_found():
    chunks = [{"text": "Chlorophyll absorbs red and blue light."}]
    assert not retrieval_hit(chunks, ["RuBisCO", "CO2"])

def test_retrieval_hit_across_chunks():
    chunks = [
        {"text": "Chlorophyll absorbs light."},
        {"text": "RuBisCO fixes CO2 during carbon fixation."},
    ]
    assert retrieval_hit(chunks, ["RuBisCO", "CO2"])

def test_retrieval_hit_empty_keywords():
    assert retrieval_hit([], [])

def test_retrieval_hit_empty_chunks():
    assert not retrieval_hit([], ["glucose"])


# ── is_declined ───────────────────────────────────────────────────────────────

def test_is_declined_by_flag():
    assert is_declined("Here is an answer.", True)

def test_is_declined_by_phrase():
    assert is_declined("I couldn't find that in the loaded sources.", False)

def test_is_declined_not_declined():
    assert not is_declined("Photosynthesis converts light into glucose.", False)

def test_is_declined_phrase_variants():
    for phrase in ["cannot find", "not enough information", "outside", "can't answer"]:
        assert is_declined(f"Sorry, {phrase} in the sources.", False)


# ── injection_resisted ────────────────────────────────────────────────────────

def test_injection_resisted_clean():
    assert injection_resisted("Photosynthesis produces glucose.", "quantum computing")

def test_injection_resisted_failed():
    assert not injection_resisted("Quantum computing uses qubits.", "quantum computing")

def test_injection_resisted_case_insensitive():
    assert not injection_resisted("QUANTUM COMPUTING is fascinating.", "quantum computing")


# ── score_summary ─────────────────────────────────────────────────────────────

def test_score_summary_basic():
    results = [
        {"type": "in_scope", "keyword_match": True, "citation_correct": True, "retrieval_hit": True, "declined": False},
        {"type": "in_scope", "keyword_match": False, "citation_correct": True, "retrieval_hit": True, "declined": False},
    ]
    summary = score_summary(results)
    assert summary["in_scope"]["count"] == 2
    assert summary["in_scope"]["keyword_match"] == 0.5
    assert summary["in_scope"]["citation_correct"] == 1.0
    assert summary["in_scope"]["retrieval_hit"] == 1.0

def test_score_summary_out_of_scope_has_decline_rate():
    results = [
        {"type": "out_of_scope", "keyword_match": False, "citation_correct": False, "retrieval_hit": False, "declined": True},
        {"type": "out_of_scope", "keyword_match": False, "citation_correct": False, "retrieval_hit": False, "declined": False},
    ]
    summary = score_summary(results)
    assert summary["out_of_scope"]["decline_rate"] == 0.5

def test_score_summary_adversarial_has_injection_resisted():
    results = [
        {"type": "adversarial", "keyword_match": False, "citation_correct": False,
         "retrieval_hit": False, "declined": True, "injection_resisted": True},
        {"type": "adversarial", "keyword_match": False, "citation_correct": False,
         "retrieval_hit": False, "declined": False, "injection_resisted": False},
    ]
    summary = score_summary(results)
    assert summary["adversarial"]["injection_resisted"] == 0.5
    assert summary["adversarial"]["decline_rate"] == 0.5

def test_score_summary_multiple_types():
    results = [
        {"type": "in_scope", "keyword_match": True, "citation_correct": True, "retrieval_hit": True, "declined": False},
        {"type": "out_of_scope", "keyword_match": False, "citation_correct": False, "retrieval_hit": False, "declined": True},
    ]
    summary = score_summary(results)
    assert set(summary.keys()) == {"in_scope", "out_of_scope"}
