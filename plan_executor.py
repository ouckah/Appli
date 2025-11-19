"""
Utilities for executing a PlaywrightPlan with real browser actions.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Optional

from playwright.async_api import Page

from action_parser import PlaywrightPlan, PlaywrightStep
from page_loader import launch_browser


class PlanExecutionError(Exception):
    """Raised when a step cannot be executed."""


async def _ensure_locator(page: Page, selector: str, *, allow_multiple: bool = False):
    locator = page.locator(selector)
    count = await locator.count()
    if count == 0:
        raise PlanExecutionError(f"Selector '{selector}' did not match any nodes.")
    if count > 1 and allow_multiple:
        print(f"[warn] selector '{selector}' matched {count} nodes; using the first match.")
        return locator.first
    return locator


async def _handle_goto(page: Page, step: PlaywrightStep, wait_until: str):
    target = step.value or step.selector
    if not target:
        raise PlanExecutionError("Goto step requires a target URL in 'value' or 'selector'.")
    await page.goto(target, wait_until=wait_until)


async def _handle_click(page: Page, step: PlaywrightStep, wait_until: str):
    locator = await _ensure_locator(page, step.selector or "", allow_multiple=True)
    await locator.click()


async def _handle_fill(page: Page, step: PlaywrightStep, wait_until: str):
    if step.value is None:
        raise PlanExecutionError("Fill step requires a 'value'.")
    locator = await _ensure_locator(page, step.selector or "")
    
    # Check if it's a number input - .fill() doesn't work on number inputs
    input_type = await locator.get_attribute("type")
    if input_type == "number":
        # For number inputs, use evaluate to set the value directly
        # This triggers change events properly
        await locator.evaluate(
            "(element, value) => { element.value = value; element.dispatchEvent(new Event('input', { bubbles: true })); element.dispatchEvent(new Event('change', { bubbles: true })); }",
            str(step.value),
        )
    else:
        await locator.fill(step.value)


async def _handle_press(page: Page, step: PlaywrightStep, wait_until: str):
    locator = await _ensure_locator(page, step.selector or "", allow_multiple=True)
    if step.value:
        await locator.press(step.value)
        return
    # fallback: treat as click/spacebar toggle when no key provided
    print(f"[warn] PRESS step missing value; clicking selector {step.selector!r} instead.")
    await locator.click()


async def _handle_select(page: Page, step: PlaywrightStep, wait_until: str):
    if step.value is None:
        raise PlanExecutionError("select_option step requires a 'value'.")
    locator = await _ensure_locator(page, step.selector or "")
    
    # Try to determine if it's a native <select> or custom dropdown
    tag_name = await locator.evaluate("(el) => el.tagName.toLowerCase()")
    
    if tag_name == "select":
        # Native select - use select_option with value, label, or index
        try:
            await locator.select_option(step.value)
            return
        except Exception as e:
            # If select_option fails, try matching by visible text
            await locator.select_option(label=step.value)
            return
    else:
        # Custom dropdown - click to open, then click the option
        await locator.click()
        await page.wait_for_timeout(200)  # Wait for dropdown to open
        
        # Try to find the option by text
        option_selector = f"text={step.value}"
        option_locator = page.locator(option_selector).first
        count = await option_locator.count()
        
        if count > 0:
            await option_locator.click()
            return
        
        # Fallback: try finding in any visible dropdown/menu
        option_locator = page.locator(f"[role='option']:has-text('{step.value}')").first
        count = await option_locator.count()
        if count > 0:
            await option_locator.click()
            return
        
        raise PlanExecutionError(f"Could not find option '{step.value}' in dropdown '{step.selector}'")


async def _handle_check(page: Page, step: PlaywrightStep, wait_until: str):
    selector = step.selector or ""
    try:
        locator = await _ensure_locator(page, selector, allow_multiple=True)
        await locator.check()
        return
    except PlanExecutionError:
        pass

    # Fallbacks for label-based selectors (common for checkboxes/radios)
    label_text = None
    if "has-text(" in selector:
        label_text = selector.split("has-text(")[-1].rstrip(")'").strip("'\"")
    if label_text:
        label_loc = page.get_by_label(label_text, exact=True)
        count = await label_loc.count()
        if count == 1:
            await label_loc.click()
            return
        if count > 1:
            print(f"[warn] label '{label_text}' matched {count} elements; clicking the first.")
            await label_loc.first.click()
            return

    raise PlanExecutionError(f"Selector '{selector}' did not match any nodes.")


async def _handle_uncheck(page: Page, step: PlaywrightStep, wait_until: str):
    locator = await _ensure_locator(page, step.selector or "")
    await locator.uncheck()


async def _handle_wait_for_selector(page: Page, step: PlaywrightStep, wait_until: str):
    target_state = (step.value or "visible").lower()
    if target_state not in {"attached", "detached", "visible", "hidden"}:
        target_state = "visible"
    await page.wait_for_selector(step.selector or "", state=target_state)


async def _handle_wait_for_timeout(page: Page, step: PlaywrightStep, wait_until: str):
    try:
        duration = int(step.value or 1000)
    except ValueError as exc:
        raise PlanExecutionError("wait_for_timeout requires an integer 'value' in ms.") from exc
    await page.wait_for_timeout(duration)


async def _handle_upload(page: Page, step: PlaywrightStep, wait_until: str):
    if not step.value:
        raise PlanExecutionError("upload_file step requires a 'value' path.")
    locator = await _ensure_locator(page, step.selector or "")
    await locator.set_input_files(step.value)


ACTION_RUNNERS: dict[str, Callable[[Page, PlaywrightStep, str], Awaitable[None]]] = {
    "goto": _handle_goto,
    "click": _handle_click,
    "fill": _handle_fill,
    "press": _handle_press,
    "select_option": _handle_select,
    "check": _handle_check,
    "uncheck": _handle_uncheck,
    "wait_for_selector": _handle_wait_for_selector,
    "wait_for_timeout": _handle_wait_for_timeout,
    "upload_file": _handle_upload,
}


async def execute_plan_on_page(
    page: Page,
    plan: PlaywrightPlan,
    *,
    wait_until: str = "networkidle",
) -> None:
    """Execute the given plan on an already-initialised Playwright page."""
    for idx, step in enumerate(plan.steps, start=1):
        runner = ACTION_RUNNERS.get(step.action)
        if not runner:
            raise PlanExecutionError(f"No runner implemented for action '{step.action}'.")
        print(f"[{idx:02d}] {step.action.upper()} selector={step.selector!r} value={step.value!r}")
        await runner(page, step, wait_until)


async def execute_plan(
    plan: PlaywrightPlan,
    *,
    start_url: Optional[str] = None,
    wait_until: str = "networkidle",
    keep_browser_open: bool = False,
) -> None:
    """Spin up a browser, navigate if needed, and execute each plan step."""
    async with launch_browser() as browser:
        context = await browser.new_context()
        page = await context.new_page()

        if start_url and not any(step.action == "goto" for step in plan.steps):
            await page.goto(start_url, wait_until=wait_until)

        await execute_plan_on_page(page, plan, wait_until=wait_until)

        if keep_browser_open:
            print("\nPlan completed. Leaving the browser open—close the window to finish.")
            try:
                await page.wait_for_event("close")
            except Exception:
                pass

        await context.close()


def execute_plan_sync(*args, **kwargs):
    """Convenience wrapper for synchronous callers."""
    return asyncio.run(execute_plan(*args, **kwargs))

