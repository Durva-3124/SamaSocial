"""Course planner chat pipeline — SSE stream."""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

from app.models.course import Course, missing_intake_fields
from app.models.llm import Message
from app.services.intake import analyse_turn, intake_prompt
from app.services.llm import LLMClient, get_llm
from app.services.planner import generate_plan, refine_plan
from app.services.stores.course_store import CourseRecord

logger = logging.getLogger(__name__)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _merge_modules(current: Course, generated: Course) -> Course:
    """Return current plan with modules from generated merged in by id.

    Modules present in generated replace their counterpart in current (matched
    by id).  Modules in current that are absent from generated are kept.
    New modules in generated that have no counterpart are appended.
    This ensures a concurrent PATCH to an unchanged module is never lost.
    """
    gen_by_id = {m.id: m for m in generated.modules}
    cur_by_id = {m.id: m for m in current.modules}

    merged: list = []
    for mod in current.modules:
        merged.append(gen_by_id.get(mod.id, mod))

    for mod in generated.modules:
        if mod.id not in cur_by_id:
            merged.append(mod)

    import json as _json
    data = _json.loads(generated.model_dump_json())
    data["modules"] = [_json.loads(m.model_dump_json()) for m in merged]
    return Course.model_validate(data)


async def course_chat_stream(
    record: CourseRecord,
    message: str,
    *,
    llm: LLMClient | None = None,
) -> AsyncIterator[str]:
    """Yield SSE events for a course planning chat turn.

    Flow:
    1. Analyse turn → update intake → emit intake_state
    2. If intake complete and no plan → generate plan → emit plan_update
    3. If intake complete and plan exists and message is specific → refine → emit plan_update
    4. If intake complete and plan exists but message is ambiguous → ask clarifying question
    5. If intake incomplete → stream a clarifying question as tokens → emit done
    """
    _llm = llm or get_llm()

    # Step 1: extract intake fields and detect intent
    try:
        updated_intake, intent = await analyse_turn(
            message, record.messages, record.intake, llm=_llm
        )
    except Exception as exc:
        logger.exception("Intake analysis failed")
        yield _sse("error", {"code": "INTAKE_ERROR", "message": str(exc)})
        return

    record.intake = updated_intake
    missing = missing_intake_fields(updated_intake)
    yield _sse("intake_state", {
        "intake": updated_intake.model_dump(),
        "missing": missing,
    })

    # Persist user turn
    record.messages.append(Message(role="user", content=message))

    # Step 2/3/4: generate or refine plan
    if not missing:
        if record.plan is None:
            # Generate fresh plan
            try:
                new_plan = await generate_plan(updated_intake, llm=_llm)
            except Exception as exc:
                logger.exception("Plan generation failed")
                yield _sse("error", {"code": "PLAN_ERROR", "message": str(exc)})
                return

            async with record.lock:
                record.plan = new_plan
                record.plan_version += 1
                version = record.plan_version
                plan_dump = record.plan.model_dump()

            changed_ids = [m.id for m in new_plan.modules]
            yield _sse("plan_update", {
                "plan": plan_dump,
                "plan_version": version,
                "changed_ids": changed_ids,
            })
            assistant_reply = (
                f"I've generated your course plan: "
                f"**{new_plan.title}** — {new_plan.description}"
            )

        elif intent == "clarify":
            # Ambiguous refinement — ask for specifics, change nothing
            assistant_reply = (
                "I'd love to improve the plan! Could you be more specific? "
                "For example: 'make module 2 simpler', 'add more exercises to week 3', "
                "or 'shorten the course to 4 weeks'."
            )

        else:
            # Specific refinement — generate under lock, merge by module id
            try:
                # Read current plan snapshot before the LLM call (outside lock)
                snapshot = record.plan
                refined = await refine_plan(snapshot, message, record.messages[:-1], llm=_llm)
            except Exception as exc:
                logger.exception("Plan refinement failed")
                yield _sse("error", {"code": "PLAN_ERROR", "message": str(exc)})
                return

            async with record.lock:
                # Re-read the live plan (may have been PATCHed during generation)
                live = record.plan
                if live is not None:
                    merged = _merge_modules(live, refined)
                else:
                    merged = refined
                # Only increase version
                record.plan = merged
                record.plan_version += 1
                version = record.plan_version
                plan_dump = record.plan.model_dump()

            changed_ids = [m.id for m in refined.modules]
            yield _sse("plan_update", {
                "plan": plan_dump,
                "plan_version": version,
                "changed_ids": changed_ids,
            })
            assistant_reply = (
                f"I've updated your course plan: "
                f"**{merged.title}** — {merged.description}"
            )
    else:
        # Intake incomplete — ask for next missing field
        assistant_reply = intake_prompt(missing)

    # Stream assistant reply as tokens
    for word in assistant_reply.split(" "):
        yield _sse("token", {"text": word + " "})

    record.messages.append(Message(role="assistant", content=assistant_reply))
    yield _sse("done", {})
