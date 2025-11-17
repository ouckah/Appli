"""
Utilities for turning LLM output into executable Playwright steps.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, Optional


class ActionParserError(Exception):
    """Raised when the LLM output cannot be parsed into a valid plan."""


PLAYWRIGHT_ACTIONS: tuple[str, ...] = (
    "goto",
    "click",
    "fill",
    "press",
    "select_option",
    "check",
    "uncheck",
    "wait_for_selector",
    "wait_for_timeout",
    "upload_file",
)

PlaywrightAction = Literal[
    "goto",
    "click",
    "fill",
    "press",
    "select_option",
    "check",
    "uncheck",
    "wait_for_selector",
    "wait_for_timeout",
    "upload_file",
]


@dataclass(frozen=True)
class PlaywrightStep:
    action: PlaywrightAction
    selector: Optional[str] = None
    value: Optional[str] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class PlaywrightPlan:
    summary: str
    assumptions: list[str]
    steps: list[PlaywrightStep]
    status: str = "pending"


def _strip_code_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        # Remove leading ``` or ```json fences
        without_start = text.split("\n", 1)
        if len(without_start) == 1:
            return ""
        first_line = without_start[0]
        remainder = without_start[1]
        if first_line.startswith("```"):
            text = remainder
        if "```" in text:
            text = text.rsplit("```", 1)[0]
    return text.strip()


def _load_json_block(raw: str) -> dict:
    try:
        return json.loads(_strip_code_fence(raw))
    except json.JSONDecodeError as exc:
        raise ActionParserError(f"LLM output is not valid JSON: {exc}") from exc


def parse_playwright_plan(raw: str) -> PlaywrightPlan:
    """
    Parse the LLM response (expected to be JSON) into a PlaywrightPlan.
    """
    payload = _load_json_block(raw)
    plan_data = payload.get("plan") or payload

    summary = str(plan_data.get("summary") or "").strip()
    status = str(plan_data.get("status") or "pending").lower()
    assumptions = plan_data.get("assumptions") or []
    steps_data = plan_data.get("steps") or []

    if not summary:
        raise ActionParserError("Plan summary is missing.")

    if status not in {"pending", "confirmed", "blocked", "error"}:
        raise ActionParserError("Plan status must be one of: pending, confirmed, blocked, error.")

    if not isinstance(assumptions, list):
        raise ActionParserError("Assumptions must be a list of strings.")

    if not isinstance(steps_data, list):
        raise ActionParserError("Plan steps field must be a list.")
    if not steps_data and status == "pending":
        raise ActionParserError("Pending plans must include at least one step.")

    steps: list[PlaywrightStep] = []
    for idx, step in enumerate(steps_data):
        if not isinstance(step, dict):
            raise ActionParserError(f"Step {idx} is not an object.")

        action = step.get("action")
        selector = step.get("selector")
        value = step.get("value")
        reason = step.get("reason")

        if action not in PLAYWRIGHT_ACTIONS:
            raise ActionParserError(f"Unsupported action '{action}' in step {idx}.")

        if action not in {"wait_for_timeout"} and not selector:
            raise ActionParserError(f"Step {idx} requires a selector.")

        steps.append(
            PlaywrightStep(
                action=action,  # type: ignore[arg-type]
                selector=selector,
                value=value,
                reason=reason,
            )
        )

    return PlaywrightPlan(
        summary=summary,
        assumptions=[str(a) for a in assumptions],
        steps=steps,
        status=status,
    )

