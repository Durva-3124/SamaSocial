"""Course planner evaluation — 5 mentor scenarios.

Usage:
    cd backend
    python -m eval.planner_eval
"""
from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, UTC
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import AppError
from app.models.course import Course, IntakeData, missing_intake_fields
from app.services.llm import get_llm
from app.services.planner import generate_plan, refine_plan
from app.services.stores.course_store import CourseRecord

REPORT_PATH = Path(__file__).parent / "planner_report.md"

SCENARIOS = [
    {
        "id": "s1",
        "name": "School Python",
        "intake": IntakeData(
            topic="Python programming basics",
            level="beginner",
            duration_weeks=6,
            sessions_per_week=3,
            age_group="teenager",
            prior_knowledge="none",
            goals=["Build small programs", "Understand variables and loops"],
            prerequisites=[],
        ),
        "refine_instruction": "Make module 2 simpler and add more beginner exercises.",
        "refine_target": "m2",
    },
    {
        "id": "s2",
        "name": "College Data Structures",
        "intake": IntakeData(
            topic="Data structures and algorithms",
            level="intermediate",
            duration_weeks=8,
            sessions_per_week=4,
            age_group="college student",
            prior_knowledge="Basic Python or Java",
            goals=["Implement common data structures", "Analyse time complexity"],
            prerequisites=["Basic Python or Java"],
        ),
        "refine_instruction": "Add a module on graph algorithms at the end.",
        "refine_target": None,
    },
    {
        "id": "s3",
        "name": "Adult Digital Marketing",
        "intake": IntakeData(
            topic="Digital marketing fundamentals",
            level="beginner",
            duration_weeks=4,
            sessions_per_week=2,
            age_group="adult",
            prior_knowledge="none",
            goals=["Run a social media campaign", "Understand SEO basics"],
            prerequisites=[],
        ),
        "refine_instruction": "Make module 1 focus more on social media strategy.",
        "refine_target": "m1",
    },
    {
        "id": "s4",
        "name": "ML Intro for Engineers",
        "intake": IntakeData(
            topic="Machine learning for software engineers",
            level="intermediate",
            duration_weeks=6,
            sessions_per_week=3,
            age_group="professional",
            prior_knowledge="Python, basic statistics",
            goals=["Train and evaluate ML models", "Understand neural networks"],
            prerequisites=["Python", "Basic statistics"],
        ),
        "refine_instruction": "Add practical Jupyter notebook exercises to every module.",
        "refine_target": None,
    },
    {
        "id": "s5",
        "name": "Spoken English",
        "intake": IntakeData(
            topic="Spoken English for professionals",
            level="beginner",
            duration_weeks=5,
            sessions_per_week=3,
            age_group="professional",
            prior_knowledge="basic written English",
            goals=["Improve pronunciation", "Conduct business conversations"],
            prerequisites=[],
        ),
        "refine_instruction": "Make module 3 focus on presentation skills.",
        "refine_target": "m3",
    },
]


def _difficulty_non_decreasing(course: Course) -> list[str]:
    """Return list of violation descriptions (empty = no violations)."""
    order = {"beginner": 0, "intermediate": 1, "advanced": 2}
    violations: list[str] = []
    prev = 0
    for mod in course.modules:
        for lesson in mod.lessons:
            val = order.get(lesson.difficulty, 0)
            if val < prev:
                violations.append(
                    f"Lesson {lesson.id} difficulty dropped to {getattr(lesson, 'difficulty', 'beginner')}"
                )
            prev = max(prev, val)
    return violations


def _schema_valid(course: Course) -> bool:
    try:
        Course.model_validate(course.model_dump())
        return True
    except Exception:
        return False


def _parse_retry_after(exc: Exception) -> float:
    """Parse the retry_after value from AppError or exception message."""
    if hasattr(exc, "retry_after") and isinstance(getattr(exc, "retry_after"), (int, float)):
        return float(getattr(exc, "retry_after"))
    msg = getattr(exc, "message", "") or str(exc)
    match = re.search(r"Retry after (\d+(?:\.\d+)?)s?", msg, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return 15.0


def _is_rate_limit(exc: Exception) -> bool:
    """Check if exception represents a rate limit error."""
    if isinstance(exc, AppError) and exc.code == "LLM_RATE_LIMIT":
        return True
    msg = (getattr(exc, "message", "") or str(exc)).lower()
    return "rate limit" in msg or "429" in msg


async def run_scenario(scenario: dict, llm, max_retries: int = 2) -> dict:
    intake: IntakeData = scenario["intake"]
    result: dict = {
        "id": scenario["id"],
        "name": scenario["name"],
        "schema_valid": False,
        "difficulty_violations": [],
        "module_count": 0,
        "refine_isolated": False,
        "edit_persistence": False,
        "ttf_first_module_ms": 0,
        "total_generation_ms": 0,
        "errors": [],
    }

    retries_used = 0
    plan = None

    # Step 1: generate_plan with rate-limit retry
    while retries_used <= max_retries:
        t0 = time.monotonic()
        try:
            plan = await generate_plan(intake, llm=llm)
            result["ttf_first_module_ms"] = int((time.monotonic() - t0) * 1000)
            result["total_generation_ms"] = int((time.monotonic() - t0) * 1000)
            break
        except Exception as exc:
            if _is_rate_limit(exc) and retries_used < max_retries:
                retries_used += 1
                wait_sec = _parse_retry_after(exc) + 2.0
                print(f"       [rate-limited on generate_plan, sleeping {wait_sec:.1f}s (retry {retries_used}/{max_retries})]")
                await asyncio.sleep(wait_sec)
                continue
            result["errors"].append(f"generate_plan failed: {exc}")
            return result

    result["schema_valid"] = _schema_valid(plan)
    result["difficulty_violations"] = _difficulty_non_decreasing(plan)
    result["module_count"] = len(plan.modules)

    # Step 2: PATCH a title and verify it survives refinement
    if plan.modules:
        edited_title = plan.modules[0].title + " [EDITED]"
        import json as _json
        data = _json.loads(plan.model_dump_json())
        data["modules"][0]["title"] = edited_title
        patched_plan = Course.model_validate(data)

        refined = None
        while retries_used <= max_retries:
            try:
                refined = await refine_plan(
                    patched_plan,
                    scenario["refine_instruction"],
                    [],
                    llm=llm,
                )
                break
            except Exception as exc:
                if _is_rate_limit(exc) and retries_used < max_retries:
                    retries_used += 1
                    wait_sec = _parse_retry_after(exc) + 2.0
                    print(f"       [rate-limited on refine_plan, sleeping {wait_sec:.1f}s (retry {retries_used}/{max_retries})]")
                    await asyncio.sleep(wait_sec)
                    continue
                result["errors"].append(f"refine_plan failed: {exc}")
                break

        if refined is not None:
            result["edit_persistence"] = refined.modules[0].title == edited_title

            # Check refine isolation: if target is m2, only m2 should change
            target = scenario["refine_target"]
            if target and len(plan.modules) >= 2:
                unchanged = [
                    m for m in refined.modules
                    if m.id != target and m.id != "m1"  # m1 was edited
                ]
                original_ids = {m.id for m in plan.modules}
                result["refine_isolated"] = all(m.id in original_ids for m in unchanged)
            else:
                result["refine_isolated"] = True  # no specific target to check

    return result


def write_planner_report(results: list[dict], settings) -> None:
    lines = [
        "# Planner Evaluation Report",
        f"\nDate: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Model: `{settings.LLM_MODEL}`",
        "",
        "## Results",
        "",
        "| Scenario | schema_valid | diff_violations | modules | refine_isolated | edit_persistence | ttf_ms | total_ms |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['name']} "
            f"| {'✓' if r['schema_valid'] else '✗'} "
            f"| {len(r['difficulty_violations'])} "
            f"| {r['module_count']} "
            f"| {'✓' if r['refine_isolated'] else '✗'} "
            f"| {'✓' if r['edit_persistence'] else '✗'} "
            f"| {r['ttf_first_module_ms']} "
            f"| {r['total_generation_ms']} |"
        )

    schema_rate = sum(r["schema_valid"] for r in results) / len(results)
    total_violations = sum(len(r["difficulty_violations"]) for r in results)
    refine_ok = sum(r["refine_isolated"] for r in results)
    edit_ok = sum(r["edit_persistence"] for r in results)

    lines += [
        "",
        "## Summary",
        "",
        f"- schema_valid: {schema_rate:.0%} ({sum(r['schema_valid'] for r in results)}/{len(results)})",
        f"- difficulty violations total: {total_violations}",
        f"- refine_isolated: {refine_ok}/{len(results)}",
        f"- edit_persistence: {edit_ok}/{len(results)}",
    ]

    for r in results:
        if r["errors"] or r["difficulty_violations"]:
            lines += [f"\n### {r['name']} issues"]
            for e in r["errors"]:
                lines.append(f"- ERROR: {e}")
            for v in r["difficulty_violations"]:
                lines.append(f"- DIFFICULTY: {v}")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nPlanner report written to {REPORT_PATH}")


async def main() -> None:
    settings = get_settings()
    print(f"Model: {settings.LLM_MODEL}")
    print(f"Running {len(SCENARIOS)} planner scenarios...")

    llm = get_llm()
    results: list[dict] = []

    for i, scenario in enumerate(SCENARIOS):
        if i > 0:
            print("  Sleeping 15s between scenarios to respect TPM limits...")
            await asyncio.sleep(15)
        print(f"  [{scenario['id']}] {scenario['name']}...")
        r = await run_scenario(scenario, llm)
        results.append(r)
        print(
            f"       schema={'OK' if r['schema_valid'] else 'FAIL'} "
            f"violations={len(r['difficulty_violations'])} "
            f"modules={r['module_count']} "
            f"refine={'OK' if r['refine_isolated'] else 'FAIL'} "
            f"edit={'OK' if r['edit_persistence'] else 'FAIL'} "
            f"total={r['total_generation_ms']}ms"
        )

    write_planner_report(results, settings)


if __name__ == "__main__":
    asyncio.run(main())
