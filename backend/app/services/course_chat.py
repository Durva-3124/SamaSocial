"""Course planner chat pipeline — SSE stream."""
import json
import logging
from collections.abc import AsyncIterator

from app.models.course import missing_intake_fields
from app.models.llm import Message
from app.services.intake import analyse_turn, intake_prompt
from app.services.llm import LLMClient, get_llm
from app.services.planner import generate_plan, refine_plan
from app.services.stores.course_store import CourseRecord

logger = logging.getLogger(__name__)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


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
    3. If intake complete and plan exists → refine plan → emit plan_update
    4. If intake incomplete → stream a clarifying question as tokens → emit done
    """
    _llm = llm or get_llm()

    # Step 1: extract intake fields
    try:
        updated_intake = await analyse_turn(
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

    # Step 2/3: generate or refine plan
    if not missing:
        try:
            if record.plan is None:
                new_plan = await generate_plan(updated_intake, llm=_llm)
            else:
                new_plan = await refine_plan(
                    record.plan, message, record.messages[:-1], llm=_llm
                )
            record.plan = new_plan
            record.plan_version += 1

            # Collect changed module/lesson ids (all on first generation)
            changed_ids = [m.id for m in new_plan.modules]
            yield _sse("plan_update", {
                "plan": new_plan.model_dump(),
                "plan_version": record.plan_version,
                "changed_ids": changed_ids,
            })

            assistant_reply = (
                f"I've {'generated' if record.plan_version == 1 else 'updated'} your course plan: "
                f"**{new_plan.title}** — {new_plan.description}"
            )
        except Exception as exc:
            logger.exception("Plan generation failed")
            yield _sse("error", {"code": "PLAN_ERROR", "message": str(exc)})
            return
    else:
        # Intake incomplete — ask for next missing field
        assistant_reply = intake_prompt(missing)

    # Stream assistant reply as tokens
    for word in assistant_reply.split(" "):
        yield _sse("token", {"text": word + " "})

    record.messages.append(Message(role="assistant", content=assistant_reply))
    yield _sse("done", {})
