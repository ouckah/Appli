import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import Optional

from action_parser import PlaywrightPlan, PlaywrightStep
from form_parser import extract_semantic_dom
from model import generate_playwright_plan
from page_loader import launch_browser
from plan_executor import execute_plan_on_page

# ===== Configurable constants =====
URL = "https://careers.point72.com/CSJobDetail?jobName=software-engineer-2026-grad&jobCode=IVS-0013868&location=New+York&locale=English&retURL=/CSCareerSearch&utm_campaign=google_jobs_apply&utm_source=google_jobs_apply&utm_medium=organic"
HEADED = True
WAIT_UNTIL = "load"
EXTRA_CONTEXT = "Prioritize remote-friendly roles."
EXECUTE_PLAN = True  # Set True to run the generated plan against a live page
KEEP_BROWSER_OPEN = True  # Leave the browser window open after execution
MAX_PLAN_ITERATIONS = 4  # Guardrail to avoid runaway loops
PRINT_SEMANTICS = True  # Dump the semantic DOM details each iteration
PRINT_HTML = False  # Dump the raw HTML snapshot (careful: noisy!)
UPLOAD_FIXTURE_PATH = Path("fixtures/dummy_resume.pdf").resolve()

def _format_step(step: PlaywrightStep, index: int) -> dict:
    """Return a JSON-serialisable dict for pretty printing."""
    payload = {
        "action": step.action,
        "selector": step.selector,
        "value": step.value,
        "reason": step.reason,
    }
    return {f"step_{index:02d}": payload}


def _interactive_summary(dom_snapshot: dict) -> tuple[str, int]:
    inputs = dom_snapshot.get("inputs", [])
    textareas = dom_snapshot.get("textareas", [])
    selects = dom_snapshot.get("selects", [])
    summary_lines = [
        f"Detected fields: inputs={len(inputs)}, textareas={len(textareas)}, selects={len(selects)}."
    ]
    interactive_count = len(inputs) + len(textareas) + len(selects)
    if interactive_count:
        summary_lines.append(
            "Do NOT mark status='confirmed' while interactive form fields remain. "
            "Only set status='confirmed' when the DOM clearly shows submission confirmation text "
            "(e.g., 'Thank you for applying', 'Application submitted')."
        )
    return "\n".join(summary_lines), interactive_count


async def _build_plan_from_page(
    html: str,
    *,
    extra_context: Optional[str] = None,
) -> tuple[PlaywrightPlan, dict]:
    semantic_dom = extract_semantic_dom(html)
    semantics_text = json.dumps(semantic_dom, indent=2)
    summary_text, _ = _interactive_summary(semantic_dom)
    combined_context = "\n\n".join(
        [text for text in (extra_context, summary_text) if text]
    ).strip()
    plan = generate_playwright_plan(
        semantics_text,
        extra_context=combined_context or None,
    )
    return plan, semantic_dom


def _apply_upload_fixtures(plan: PlaywrightPlan) -> PlaywrightPlan:
    if not UPLOAD_FIXTURE_PATH.exists():
        return plan

    updated_steps: list[PlaywrightStep] = []
    changed = False
    for step in plan.steps:
        if step.action == "upload_file":
            updated_steps.append(replace(step, value=str(UPLOAD_FIXTURE_PATH)))
            changed = True
        else:
            updated_steps.append(step)

    if changed:
        return replace(plan, steps=updated_steps)
    return plan


def render_plan(plan: PlaywrightPlan) -> str:
    """Convert a PlaywrightPlan into a friendly multiline string."""
    data = {
        "status": plan.status,
        "summary": plan.summary,
        "assumptions": plan.assumptions,
        "steps": [_format_step(step, idx + 1) for idx, step in enumerate(plan.steps)],
    }
    return json.dumps(data, indent=2)


async def main():
    if not URL:
        raise SystemExit("URL must be set to fetch the job page.")

    async with launch_browser(headless=not HEADED) as browser:
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()
        await page.goto(URL, wait_until=WAIT_UNTIL)

        plan = None
        for iteration in range(1, MAX_PLAN_ITERATIONS + 1):
            print(f"\n=== Plan iteration {iteration}/{MAX_PLAN_ITERATIONS} ===")
            html = await page.content()
            plan, dom_snapshot = await _build_plan_from_page(
                html,
                extra_context=EXTRA_CONTEXT,
            )
            plan = _apply_upload_fixtures(plan)
            if PRINT_HTML:
                print("Raw HTML snapshot:")
                print(html[:2000] + ("\n...[truncated]..." if len(html) > 2000 else ""))
            _, interactive_count = _interactive_summary(dom_snapshot)

            if PRINT_SEMANTICS:
                print("Semantic snapshot:")
                print(json.dumps(dom_snapshot, indent=2))

            if plan.status == "confirmed" and interactive_count:
                print(
                    "Plan marked status=confirmed while interactive fields remain; "
                    "forcing status back to pending."
                )
                plan = replace(plan, status="pending")

            print(render_plan(plan))

            if plan.status == "confirmed":
                print("LLM indicates the application is confirmed. Stopping loop.")
                break
            if plan.status == "blocked":
                print("LLM reports the flow is blocked. Stopping to avoid wasted calls.")
                break
            if not plan.steps:
                print("LLM returned no steps to execute. Stopping.")
                break
            if not EXECUTE_PLAN:
                print("EXECUTE_PLAN disabled; stopping after plan generation.")
                break

            await execute_plan_on_page(
                page,
                plan,
                wait_until=WAIT_UNTIL,
            )

        else:
            print(
                f"Reached MAX_PLAN_ITERATIONS={MAX_PLAN_ITERATIONS}. "
                "Aborting to prevent runaway loops/costs."
            )

        if KEEP_BROWSER_OPEN:
            print("Leaving the browser open; close the window when you're done reviewing.")
            try:
                await page.wait_for_event("close")
            except Exception:
                pass

        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
