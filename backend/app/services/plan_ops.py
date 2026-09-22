"""Plan mutation helpers: whitelist-gated JSON Pointer patching."""
from __future__ import annotations

import json
import re

from app.core.errors import AppError
from app.models.course import Course

# Patterns of pointer segments that are editable.
# Each pattern matches the FULL normalised pointer (leading slash stripped,
# segments joined with "/").
# Wildcards: * matches a single numeric index or any string segment.
_EDITABLE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^title$"),
    re.compile(r"^description$"),
    re.compile(r"^goals/\d+$"),
    re.compile(r"^modules/\d+/title$"),
    re.compile(r"^modules/\d+/description$"),
    re.compile(r"^modules/\d+/difficulty$"),
    re.compile(r"^modules/\d+/assessment$"),
    re.compile(r"^modules/\d+/objectives/\d+$"),
    re.compile(r"^modules/\d+/prerequisites/\d+$"),
    re.compile(r"^modules/\d+/lessons/\d+/title$"),
    re.compile(r"^modules/\d+/lessons/\d+/duration_minutes$"),
    re.compile(r"^modules/\d+/lessons/\d+/difficulty$"),
    re.compile(r"^modules/\d+/lessons/\d+/practice$"),
    re.compile(r"^modules/\d+/lessons/\d+/topics/\d+$"),
    re.compile(r"^modules/\d+/lessons/\d+/objectives/\d+$"),
    re.compile(r"^modules/\d+/lessons/\d+/prerequisites/\d+$"),
]

_DIFFICULTY_VALUES = {"beginner", "intermediate", "advanced"}


def _normalise_pointer(pointer: str) -> str:
    """Decode RFC 6901 escapes and strip leading slash."""
    parts = [p.replace("~1", "/").replace("~0", "~") for p in pointer.lstrip("/").split("/")]
    # Reject path traversal attempts
    if any(p in ("", ".", "..") for p in parts):
        raise AppError("INVALID_VALUE", f"Invalid JSON pointer: {pointer!r}", 422)
    return "/".join(parts)


def _is_editable(normalised: str) -> bool:
    return any(pat.match(normalised) for pat in _EDITABLE_PATTERNS)


def _validate_value(normalised: str, value: object) -> None:
    """Raise 422 if the value is wrong for the target field."""
    leaf = normalised.rsplit("/", 1)[-1]
    if leaf == "difficulty":
        if not isinstance(value, str) or value not in _DIFFICULTY_VALUES:
            raise AppError(
                "INVALID_VALUE",
                f"difficulty must be one of {sorted(_DIFFICULTY_VALUES)}, got {value!r}",
                422,
            )
    if leaf in ("title", "description", "assessment", "practice"):
        if not isinstance(value, str):
            raise AppError(
                "INVALID_VALUE",
                f"{leaf!r} must be a string, got {type(value).__name__}",
                422,
            )
    if leaf == "duration_minutes":
        if not isinstance(value, int) or value < 1:
            raise AppError(
                "INVALID_VALUE",
                "duration_minutes must be a positive integer",
                422,
            )


def apply_patch(plan: Course, pointer: str, value: object) -> Course:
    """Apply a whitelisted JSON Pointer patch and return a re-validated Course.

    Raises AppError 422 for non-editable paths, invalid values, or out-of-range
    indices.  Raises AppError 422 if the patched document fails Course validation.
    """
    normalised = _normalise_pointer(pointer)

    if not _is_editable(normalised):
        raise AppError(
            "FIELD_NOT_EDITABLE",
            f"The path {pointer!r} is not editable.",
            422,
        )

    _validate_value(normalised, value)

    data = json.loads(plan.model_dump_json())
    parts = normalised.split("/")
    node = data

    for part in parts[:-1]:
        if isinstance(node, list):
            try:
                idx = int(part)
                node = node[idx]
            except (ValueError, IndexError) as exc:
                raise AppError(
                    "INVALID_VALUE",
                    f"Index {part!r} out of range in {pointer!r}",
                    422,
                ) from exc
        elif isinstance(node, dict):
            if part not in node:
                raise AppError(
                    "INVALID_VALUE",
                    f"Key {part!r} not found in {pointer!r}",
                    422,
                )
            node = node[part]
        else:
            raise AppError("INVALID_VALUE", f"Cannot traverse into scalar at {pointer!r}", 422)

    last = parts[-1]
    if isinstance(node, list):
        try:
            node[int(last)] = value
        except (ValueError, IndexError) as exc:
            raise AppError(
                "INVALID_VALUE",
                f"Index {last!r} out of range in {pointer!r}",
                422,
            ) from exc
    elif isinstance(node, dict):
        node[last] = value
    else:
        raise AppError("INVALID_VALUE", f"Cannot set value on scalar at {pointer!r}", 422)

    try:
        return Course.model_validate(data)
    except Exception as exc:
        raise AppError("INVALID_VALUE", f"Patch produced an invalid plan: {exc}", 422) from exc
