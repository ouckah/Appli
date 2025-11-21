"""
Utilities for executing a PlaywrightPlan with real browser actions.
"""

from __future__ import annotations

import asyncio
from difflib import SequenceMatcher
from typing import Awaitable, Callable, Optional

from playwright.async_api import Page

from action_parser import PlaywrightPlan, PlaywrightStep
from models import DropdownSelectionModel
from page_loader import launch_browser

# Model instance for dropdown selection
dropdown_selection_model = DropdownSelectionModel()


async def extract_filled_fields(page: Page, semantic_dom: dict) -> dict[str, str]:
    """Extract currently filled field values from the page.
    
    Args:
        page: The Playwright page
        semantic_dom: The semantic DOM snapshot containing field metadata
        
    Returns:
        A dictionary mapping field selectors to their current values
    """
    filled_fields = {}
    
    # Extract filled values from inputs
    inputs = semantic_dom.get("inputs", [])
    for input_data in inputs:
        selector = None
        # Try ID first (most reliable)
        if input_data.get("id"):
            selector = f"#{input_data['id']}"
        elif input_data.get("name"):
            selector = f"[name='{input_data['name']}']"
        elif input_data.get("css"):
            selector = input_data["css"]
        
        if selector:
            try:
                locator = page.locator(selector).first
                count = await locator.count()
                if count > 0:
                    # Try to get value (works for inputs and textareas)
                    try:
                        value = await locator.input_value()
                        if value and value.strip():
                            filled_fields[selector] = value.strip()
                    except Exception:
                        # Try text content as fallback
                        try:
                            value = await locator.text_content()
                            if value and value.strip():
                                filled_fields[selector] = value.strip()
                        except Exception:
                            pass
            except Exception:
                pass
    
    # Extract filled values from textareas
    textareas = semantic_dom.get("textareas", [])
    for textarea_data in textareas:
        selector = None
        if textarea_data.get("id"):
            selector = f"#{textarea_data['id']}"
        elif textarea_data.get("name"):
            selector = f"[name='{textarea_data['name']}']"
        
        if selector:
            try:
                locator = page.locator(selector).first
                count = await locator.count()
                if count > 0:
                    try:
                        value = await locator.input_value()
                        if value and value.strip():
                            filled_fields[selector] = value.strip()
                    except Exception:
                        pass
            except Exception:
                pass
    
    # Extract filled values from selects
    selects = semantic_dom.get("selects", [])
    for select_data in selects:
        selector = None
        if select_data.get("id"):
            selector = f"#{select_data['id']}"
        elif select_data.get("name"):
            selector = f"[name='{select_data['name']}']"
        
        if selector:
            try:
                locator = page.locator(selector).first
                count = await locator.count()
                if count > 0:
                    try:
                        value = await locator.input_value()
                        if value and value.strip():
                            filled_fields[selector] = value.strip()
                    except Exception:
                        # Try selected option text
                        try:
                            selected_option = await locator.locator("option:checked").first.text_content()
                            if selected_option and selected_option.strip():
                                filled_fields[selector] = selected_option.strip()
                        except Exception:
                            pass
            except Exception:
                pass
    
    return filled_fields


class PlanExecutionError(Exception):
    """Raised when a step cannot be executed."""


async def _ensure_locator(page: Page, selector: str, *, allow_multiple: bool = False):
    # Fix invalid CSS selectors: IDs starting with digits are invalid in CSS
    # Convert #123 to [id="123"] format
    fixed_selector = selector
    if selector.startswith("#") and len(selector) > 1 and selector[1].isdigit():
        # Extract the ID value (everything after #)
        id_value = selector[1:]
        fixed_selector = f'[id="{id_value}"]'
        if selector != fixed_selector:
            print(f"[warn] Fixed invalid selector '{selector}' -> '{fixed_selector}' (CSS IDs cannot start with digits)")
    
    locator = page.locator(fixed_selector)
    count = await locator.count()
    if count == 0:
        raise PlanExecutionError(f"Selector '{selector}' (fixed to '{fixed_selector}') did not match any nodes.")
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


def _fuzzy_match(target: str, options: list[str]) -> tuple[Optional[str], float]:
    """Find the option that best matches the target string using fuzzy matching with semantic equivalence."""
    if not options:
        return None, 0.0
    
    best_match = None
    best_ratio = 0.0
    
    target_lower = target.lower()
    
    # Semantic equivalence groups - phrases that mean the same thing
    semantic_groups = [
        {"prefer not to say", "decline to self verify", "decline to answer", "prefer not to answer", 
         "do not wish to answer", "no response", "not specified", "unspecified", "other"},
        {"yes", "y", "true", "agree", "accept", "confirm"},
        {"no", "n", "false", "disagree", "decline", "reject", "deny"},
        {"other", "others", "other (please specify)", "other (specify)", "not listed", "none of the above"},
    ]
    
    # Find which semantic group the target belongs to (if any)
    target_group = None
    for group in semantic_groups:
        if any(phrase in target_lower for phrase in group):
            target_group = group
            break
    
    for option in options:
        option_lower = option.lower()
        ratio = SequenceMatcher(None, target_lower, option_lower).ratio()
        
        # Semantic equivalence bonus - if both are in the same semantic group, boost the ratio
        if target_group:
            option_in_group = any(phrase in option_lower for phrase in target_group)
            if option_in_group:
                ratio = max(ratio, 0.85)  # High confidence for semantic matches
        
        # Bonus if target is contained in option (for "United States" matching "United States +1")
        if target_lower in option_lower:
            ratio = max(ratio, 0.8)
        
        # Bonus if option is contained in target
        if option_lower in target_lower:
            ratio = max(ratio, 0.8)
        
        # Check for key semantic words even if not exact match
        key_words = ["prefer", "decline", "not", "other", "none", "unspecified"]
        target_has_key = any(word in target_lower for word in key_words)
        option_has_key = any(word in option_lower for word in key_words)
        if target_has_key and option_has_key:
            # Both have similar semantic meaning words
            if "prefer" in target_lower and "prefer" in option_lower:
                ratio = max(ratio, 0.75)
            if "decline" in target_lower and "decline" in option_lower:
                ratio = max(ratio, 0.75)
            if "other" in target_lower and "other" in option_lower:
                ratio = max(ratio, 0.75)
        
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = option
    
    return best_match, best_ratio


async def _extract_dropdown_options(page: Page, dropdown_container=None) -> list[str]:
    """Extract all available options from the currently visible dropdown menu.
    
    Args:
        page: The Playwright page
        dropdown_container: Optional locator for the dropdown container to scope the search
    """
    options = []
    
    # Try multiple selectors to find dropdown options - ordered by specificity
    option_selectors = [
        "[role='option']",
        "li[role='option']",
        "div[role='option']",
        "span[role='option']",
        "li",
        "div[class*='option']",
        "[class*='option']",
        "[class*='dropdown-item']",
        "[class*='select-option']",
        "[class*='menu-item']",
        "div[class*='item']",
        "span[class*='item']",
    ]
    
    # Also try to find options within common dropdown structures
    structure_selectors = [
        "[role='listbox']",
        "[role='menu']",
        "[role='combobox']",
        "[class*='dropdown-menu']",
        "[class*='select-dropdown']",
        "[class*='options-container']",
    ]
    
    # First try within dropdown container if provided
    search_locators = []
    if dropdown_container:
        search_locators.append(dropdown_container)
        # Also try finding nested containers within the dropdown
        for structure_selector in structure_selectors:
            try:
                nested = dropdown_container.locator(structure_selector).first
                count = await nested.count()
                if count > 0:
                    search_locators.append(nested)
            except Exception:
                continue
    
    # Also search globally if no container or as fallback
    search_locators.append(page)
    
    for search_locator in search_locators:
        for selector in option_selectors:
            try:
                option_elements = search_locator.locator(selector)
                count = await option_elements.count()
                
                if count > 0:
                    for i in range(count):
                        try:
                            element = option_elements.nth(i)
                            
                            # Check if element is visible
                            is_visible = await element.is_visible()
                            if not is_visible:
                                continue
                            
                            # Get text - try inner_text first, fallback to text_content
                            try:
                                text = await element.inner_text()
                            except Exception:
                                text = await element.text_content()
                            
                            text = text.strip() if text else ""
                            
                            # Skip if empty or too short (likely not an option)
                            if text and len(text) > 0 and text not in options:
                                # Filter out common non-option text
                                if not any(skip in text.lower() for skip in ["search", "filter", "loading", "no results"]):
                                    options.append(text)
                        except Exception:
                            continue
                    
                    if options:
                        return options  # Return as soon as we find options
            except Exception:
                continue
    
    return options


async def _handle_select(page: Page, step: PlaywrightStep, wait_until: str, user_info: Optional[dict] = None):
    if step.value is None:
        raise PlanExecutionError("select_option step requires a 'value'.")
    locator = await _ensure_locator(page, step.selector or "")
    
    # Get field name/label for LLM context
    field_name = step.selector or "dropdown"
    try:
        # Try to get label from associated label element
        label_text = await locator.evaluate("""
            (el) => {
                const id = el.id;
                if (id) {
                    const label = document.querySelector(`label[for="${id}"]`);
                    if (label) return label.textContent.trim();
                }
                // Try aria-label
                if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
                // Try parent label
                const parentLabel = el.closest('label');
                if (parentLabel) return parentLabel.textContent.trim();
                return null;
            }
        """)
        if label_text:
            field_name = label_text
    except Exception:
        pass
    
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
        # Custom dropdown workflow:
        # Store reference to original dropdown field to ensure value goes to correct input
        original_dropdown_selector = step.selector or ""
        
        # First, check if the value is already set correctly (avoid unnecessary work)
        try:
            existing_value = await locator.input_value() or await locator.get_attribute("value") or await locator.text_content()
            if existing_value:
                existing_value = existing_value.strip()
                if (
                    existing_value.lower() == step.value.lower() or
                    step.value.lower() in existing_value.lower() or
                    existing_value.lower() in step.value.lower() or
                    (existing_value and len(existing_value) > 0)  # Any non-empty value means field is filled
                ):
                    print(f"[info] Field already has value '{existing_value}' matching '{step.value}', skipping")
                    return
        except Exception:
            pass  # Continue if we can't check
        
        # 1. Click to open dropdown (ensure we're clicking the correct field)
        await locator.click()
        
        # Wait for dropdown menu to appear
        dropdown_indicators = [
            "[role='listbox']",
            "[role='menu']",
            "[role='combobox']",
            ".dropdown-menu",
            ".select-dropdown",
            "[data-testid*='dropdown']",
            "[class*='dropdown']",
            "[class*='menu']",
        ]
        
        dropdown_appeared = False
        for indicator in dropdown_indicators:
            try:
                await page.wait_for_selector(indicator, state="visible", timeout=1000)
                dropdown_appeared = True
                break
            except Exception:
                continue
        
        # If no specific indicator found, wait a bit for dropdown to render
        if not dropdown_appeared:
            await page.wait_for_timeout(300)
        
        # 2. Find the dropdown menu container first
        dropdown_container = None
        for indicator in dropdown_indicators:
            try:
                container = page.locator(indicator).first
                count = await container.count()
                if count > 0 and await container.is_visible():
                    dropdown_container = container
                    print(f"[info] Found dropdown container using indicator: {indicator}")
                    break
            except Exception:
                continue
        
        # Fallback: if no container found, try to find it by looking for elements near the clicked element
        if not dropdown_container:
            try:
                # Try to find a dropdown container that's a parent or sibling of the clicked element
                # Use locator chaining to find nearby dropdown containers
                for indicator in dropdown_indicators:
                    try:
                        # Look for dropdown containers that might be related to our element
                        # Try finding it as a sibling or in a nearby container
                        nearby_container = locator.locator(f".. {indicator}, .. .. {indicator}").first
                        count = await nearby_container.count()
                        if count > 0 and await nearby_container.is_visible():
                            dropdown_container = nearby_container
                            print(f"[info] Found dropdown container via proximity: {indicator}")
                            break
                    except Exception:
                        continue
            except Exception as e:
                print(f"[warn] Could not find dropdown container via proximity: {e}")
        
        if not dropdown_container:
            print(f"[warn] Could not find specific dropdown container, will search globally (may match wrong dropdown)")
        
        # 3. Check if this is a searchable/filterable dropdown
        # Look for search input field ONLY inside the dropdown menu container
        search_input = None
        search_input_selectors = [
            "input[type='search']",
            "input[type='text']",
            "input[placeholder*='search' i]",
            "input[placeholder*='filter' i]",
            "input[placeholder*='type' i]",
            "[class*='search'] input",
            "[class*='filter'] input",
            "input",
        ]
        
        if dropdown_container:
            # Scope search to within the dropdown container ONLY
            for selector in search_input_selectors:
                try:
                    candidate = dropdown_container.locator(selector).first
                    count = await candidate.count()
                    if count > 0:
                        is_visible = await candidate.is_visible()
                        if is_visible:
                            # Additional check: verify it's actually inside the dropdown (not accidentally matching)
                            parent_role = await candidate.evaluate("(el) => el.closest('[role=\"listbox\"], [role=\"menu\"], [role=\"combobox\"]')?.getAttribute('role')")
                            if parent_role or dropdown_container:
                                search_input = candidate
                                print(f"[info] Found searchable dropdown, using search input inside dropdown: {selector}")
                                break
                except Exception:
                    continue
        else:
            # Fallback: try scoped searches if we couldn't find a container
            for selector in search_input_selectors:
                try:
                    # Only match inputs that are definitely inside dropdowns (scoped selectors)
                    candidate = page.locator(f"[role='listbox'] {selector}, [role='menu'] {selector}, .dropdown-menu {selector}, [role='combobox'] {selector}").first
                    count = await candidate.count()
                    if count > 0:
                        is_visible = await candidate.is_visible()
                        if is_visible:
                            search_input = candidate
                            print(f"[info] Found searchable dropdown, using scoped search input: {selector}")
                            break
                except Exception:
                    continue
        
        # Check if this is a combobox dropdown - the field itself IS the search input for comboboxes
        is_combobox = False
        try:
            # Check if the original locator itself has role='combobox'
            locator_role = await locator.get_attribute("role")
            if locator_role == "combobox":
                is_combobox = True
            # Or check if the dropdown container is a combobox
            elif dropdown_container:
                container_role = await dropdown_container.evaluate("(el) => el.getAttribute('role')")
                if container_role == "combobox":
                    is_combobox = True
        except Exception:
            pass
        
        if search_input and not is_combobox:
            try:
                search_id = await search_input.get_attribute("id")
                original_id = await locator.get_attribute("id")
                if search_id and original_id and search_id == original_id:
                    # Same element - not a search input, it's the dropdown field itself
                    # But for comboboxes, this is expected - use it anyway
                    print(f"[info] Search input is the dropdown field itself, checking if combobox")
                    search_input = None
            except Exception:
                pass
        
        # For comboboxes, the field itself is the search input - type directly into it
        if is_combobox and not search_input:
            print(f"[info] Combobox detected, using the field itself as search input")
            search_input = locator
        
        # 3. For text input dropdowns: Extract options, use LLM to select, type and press Enter
        if search_input:
            # Extract available options first
            available_options = await _extract_dropdown_options(page, dropdown_container=dropdown_container)
            
            if available_options:
                print(f"[info] Found {len(available_options)} available options")
                
                # Use LLM to select the best matching option
                best_match = dropdown_selection_model.select_best_option(
                    field_name=field_name,
                    target_value=step.value,
                    available_options=available_options,
                    user_info=user_info,
                )
                
                if best_match and best_match in available_options:
                    print(f"[info] LLM selected: '{best_match}' for field '{field_name}'")
                    
                    # Scroll the input into view and focus it
                    try:
                        await original_locator.scroll_into_view_if_needed()
                        await page.wait_for_timeout(200)
                    except Exception:
                        pass
                    
                    # Focus the search input
                    await search_input.click()
                    await page.wait_for_timeout(200)
                    
                    # Clear any existing value
                    try:
                        await search_input.clear()
                        await page.wait_for_timeout(100)
                    except Exception:
                        pass
                    
                    # Type the LLM-selected option
                    await search_input.fill(best_match)
                    await page.wait_for_timeout(400)  # Wait for autocomplete/dropdown to process
                    
                    # Press Enter to confirm
                    await search_input.press("Enter")
                    await page.wait_for_timeout(500)  # Wait for value to be set
                    
                    print(f"[info] Entered LLM-selected value '{best_match}' and pressed Enter, moving on")
                    return
                else:
                    # LLM didn't return a valid option, try the original value
                    print(f"[warn] LLM selection failed, trying original value '{step.value}'")
                    best_match = step.value
            else:
                # No options found, just use the original value
                print(f"[warn] No options found in dropdown, using original value '{step.value}'")
                best_match = step.value
            
            # Fallback: type the value directly and press Enter
            try:
                await original_locator.scroll_into_view_if_needed()
                await page.wait_for_timeout(200)
            except Exception:
                pass
            
            await search_input.click()
            await page.wait_for_timeout(200)
            
            try:
                await search_input.clear()
                await page.wait_for_timeout(100)
            except Exception:
                pass
            
            await search_input.fill(best_match)
            await page.wait_for_timeout(400)
            await search_input.press("Enter")
            await page.wait_for_timeout(500)
            
            print(f"[info] Entered '{best_match}' and pressed Enter, moving on")
            return
        else:
            print(f"[info] Dropdown does not appear to be searchable, using direct matching")
        
        # 4. Extract available options (filtered if searchable, or all if not) - scoped to dropdown container
        options = await _extract_dropdown_options(page, dropdown_container=dropdown_container)
        
        if not options:
            # If we can't extract options, try direct matching as fallback
            print(f"[warn] Could not extract dropdown options, trying direct match for '{step.value}'")
            try:
                option_locator = page.locator(f"text={step.value}").first
                count = await option_locator.count()
                if count > 0:
                    await option_locator.scroll_into_view_if_needed()
                    await option_locator.click(timeout=2000)
                    await page.wait_for_timeout(200)
                    return
            except Exception:
                pass
        else:
            # 5. Use LLM to intelligently select the best option
            best_match = dropdown_selection_model.select_best_option(
                field_name=field_name,
                target_value=step.value,
                available_options=options,
                user_info=user_info,
            )
            
            # Fallback to fuzzy matching if LLM returns None
            if not best_match:
                print(f"[warn] LLM selection failed, falling back to fuzzy matching")
                best_match, match_ratio = _fuzzy_match(step.value, options)
                
                # Use "other" as fallback if match quality is low
                if match_ratio < 0.6:
                    print(f"[warn] Best fuzzy match was '{best_match}' (ratio: {match_ratio:.2f}), trying 'other' fallback")
                    other_match, other_ratio = _fuzzy_match("other", options)
                    if other_ratio >= 0.7:
                        best_match = other_match
                        match_ratio = other_ratio
                        print(f"[info] Using 'other' option: '{best_match}'")
                
                if best_match and match_ratio >= 0.5:
                    print(f"[info] Fuzzy match selected: '{best_match}' (ratio: {match_ratio:.2f})")
                else:
                    best_match = None
            
            if best_match:
                print(f"[info] Selected option: '{best_match}' for field '{field_name}'")
                
                # Find and click the matching option - scope to dropdown if we have a container
                option_selectors = [
                    f"text={best_match}",
                    f"[role='option']:has-text('{best_match}')",
                    f"li:has-text('{best_match}')",
                    f"[class*='option']:has-text('{best_match}')",
                ]
                
                option_clicked = False
                for selector in option_selectors:
                    try:
                        # Scope option search to dropdown container if available
                        if dropdown_container:
                            option_locator = dropdown_container.locator(selector).first
                        else:
                            option_locator = page.locator(selector).first
                        
                        count = await option_locator.count()
                        if count > 0:
                            # Verify the option is actually visible before trying to click
                            is_visible = await option_locator.is_visible()
                            if not is_visible:
                                continue
                            
                            await option_locator.scroll_into_view_if_needed()
                            await page.wait_for_timeout(100)
                            
                            # Get the option text before clicking to verify we have the right one
                            option_text = await option_locator.inner_text()
                            print(f"[info] Attempting to click option: '{option_text}'")
                            
                            try:
                                await option_locator.click(timeout=2000)
                                option_clicked = True
                            except Exception as e1:
                                try:
                                    await option_locator.click(force=True, timeout=2000)
                                    option_clicked = True
                                except Exception as e2:
                                    # If clicking fails, try keyboard navigation: arrow to highlight, then Enter
                                    print(f"[warn] Click failed, trying keyboard navigation")
                                    if search_input:
                                        # Focus the search input and press arrow down to select first option, then Enter
                                        await search_input.focus()
                                        await page.wait_for_timeout(100)
                                        # Try arrow keys to navigate to the option, then Enter
                                        for _ in range(5):  # Try up to 5 arrow presses
                                            await page.keyboard.press("ArrowDown")
                                            await page.wait_for_timeout(50)
                                        await page.keyboard.press("Enter")
                                        await page.wait_for_timeout(300)
                                        option_clicked = True
                                    else:
                                        # No search input, try pressing Enter on the option directly
                                        await option_locator.focus()
                                        await page.wait_for_timeout(100)
                                        await page.keyboard.press("Enter")
                                        await page.wait_for_timeout(300)
                                        option_clicked = True
                            
                            # Wait for dropdown to close and value to be set
                            await page.wait_for_timeout(500)
                            
                            # Re-acquire the original dropdown locator to ensure we're checking/setting the correct field
                            original_locator = await _ensure_locator(page, original_dropdown_selector)
                            
                            # Verify value was set in the original dropdown field (not First Name or other fields)
                            try:
                                current_value = await original_locator.input_value()
                                # Check if value is set (might be empty, or might contain the match)
                                if not current_value or (best_match.lower() not in current_value.lower() and current_value.lower() not in best_match.lower()):
                                    # Value not set correctly, manually set it in the correct field
                                    print(f"[warn] Value not set correctly after option click, manually setting '{best_match}' in dropdown field '{original_dropdown_selector}'")
                                    # Close any open dropdowns first
                                    await page.keyboard.press("Escape")
                                    await page.wait_for_timeout(200)
                                    await original_locator.click()
                                    await page.wait_for_timeout(200)
                                    await original_locator.fill(best_match)
                                    await page.wait_for_timeout(100)
                                    # Try pressing Enter to confirm selection
                                    await original_locator.press("Enter")
                                    await page.wait_for_timeout(200)
                                    # Trigger change events
                                    await original_locator.evaluate("(el) => { el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); }")
                                else:
                                    print(f"[info] Value '{current_value}' successfully set in dropdown field '{original_dropdown_selector}'")
                            except Exception as e:
                                # If input_value() fails (might not be an input), try getting text content
                                print(f"[warn] Could not verify value, assuming selection succeeded: {e}")
                            
                            await page.wait_for_timeout(100)
                            return
                    except Exception:
                        continue
                
                if not option_clicked:
                    # Couldn't click option, try setting directly in the original dropdown field
                    print(f"[warn] Could not click option, attempting to set value directly in dropdown field")
                    original_locator = await _ensure_locator(page, original_dropdown_selector)
                    
                    # Close any open dropdown first
                    await page.keyboard.press("Escape")
                    await page.wait_for_timeout(200)
                    
                    # Click the dropdown to open it again
                    await original_locator.click()
                    await page.wait_for_timeout(200)
                    
                    # Fill the value
                    await original_locator.fill(best_match)
                    await page.wait_for_timeout(200)
                    
                    # Try pressing Enter to confirm selection (many dropdowns require this)
                    await original_locator.press("Enter")
                    await page.wait_for_timeout(300)
                    
                    # Verify the value was set
                    try:
                        current_value = await original_locator.input_value()
                        if not current_value or (best_match.lower() not in current_value.lower() and current_value.lower() not in best_match.lower()):
                            # Enter didn't work, try clicking an option manually
                            print(f"[warn] Enter didn't set value, trying to click option after typing")
                            if dropdown_container:
                                # Look for an option matching our value
                                option = dropdown_container.locator(f"[role='option']:has-text('{best_match}'), li:has-text('{best_match}')").first
                            else:
                                option = page.locator(f"[role='option']:has-text('{best_match}'), li:has-text('{best_match}')").first
                            
                            count = await option.count()
                            if count > 0 and await option.is_visible():
                                await option.click(timeout=2000)
                                await page.wait_for_timeout(300)
                    except Exception as e:
                        print(f"[warn] Could not verify/fix value: {e}")
                    
                    # Trigger change events as final step
                    await original_locator.evaluate("(el) => { el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); }")
                    return
        
        # If all dropdown strategies failed, check if this is actually a text input
        # that the LLM incorrectly identified as a dropdown - convert to fill
        try:
            input_type = await locator.get_attribute("type")
            tag_name = await locator.evaluate("(el) => el.tagName.toLowerCase()")
            
            # If it's a text input (not readonly) or textarea, treat as fill instead
            is_text_input = (
                tag_name == "input" and 
                input_type in (None, "text", "email", "tel", "search", "url") and
                not await locator.evaluate("(el) => el.hasAttribute('readonly') || el.hasAttribute('readOnly')")
            ) or tag_name == "textarea"
            
            if is_text_input:
                print(f"[warn] select_option failed on text input '{step.selector}', converting to fill action")
                # Close any dropdown that might have opened
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(200)
                # Now fill the field instead
                await locator.fill(step.value)
                await page.wait_for_timeout(200)
                # Press Enter to confirm the selection (many dropdowns require this)
                await locator.press("Enter")
                await page.wait_for_timeout(300)
                # Trigger change events to ensure the form recognizes the value
                try:
                    await locator.evaluate("(el) => { el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); }")
                except Exception:
                    pass
                return
        except Exception as e:
            print(f"[warn] Fallback check failed: {e}")
        
        raise PlanExecutionError(f"Could not find or click option '{step.value}' in dropdown '{step.selector}'")


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
    
    selector = step.selector or ""
    locator = None
    
    # Try the provided selector first
    if selector:
        try:
            locator = await _ensure_locator(page, selector)
            await locator.set_input_files(step.value)
            return
        except Exception:
            # Selector didn't work, try fallback strategies
            pass
    
    # Fallback 1: Try to find file input by label text (simpler pattern)
    if "label:has-text(" in selector:
        try:
            # Extract label text from the selector
            label_match = selector.split("label:has-text(")[1].split(")")[0].strip("'\"")
            # Try a simpler approach: find label with text, then find file input nearby
            label_locator = page.get_by_label(label_match, exact=False)
            count = await label_locator.count()
            if count > 0:
                # Try finding file input as sibling or in parent
                file_input = label_locator.first.locator(".. input[type='file']").first
                if await file_input.count() > 0:
                    await file_input.set_input_files(step.value)
                    return
        except Exception:
            pass
    
    # Fallback 2: Try finding file input by name attribute if present
    if "[name=" in selector:
        try:
            name_match = selector.split("[name='")[1].split("']")[0]
            file_input = page.locator(f"input[type='file'][name='{name_match}']").first
            count = await file_input.count()
            if count > 0:
                await file_input.set_input_files(step.value)
                return
        except Exception:
            pass
    
    # Fallback 3: Try finding file input by ID if present
    if "#" in selector or "[id=" in selector:
        try:
            # Extract ID from selector
            id_match = None
            if "#" in selector:
                id_match = selector.split("#")[1].split()[0].split("]")[0].split("'")[0].split('"')[0]
            elif "[id=" in selector:
                id_match = selector.split("[id='")[1].split("']")[0]
            
            if id_match:
                file_input = page.locator(f"input[type='file'][id='{id_match}']").first
                count = await file_input.count()
                if count > 0:
                    await file_input.set_input_files(step.value)
                    return
        except Exception:
            pass
    
    # Fallback 4: Try XPath if selector contains xpath
    if "xpath" in selector.lower() or "//" in selector:
        try:
            xpath_match = selector.split("//")[-1] if "//" in selector else None
            if xpath_match:
                file_input = page.locator(f"xpath=//{xpath_match}")
                count = await file_input.count()
                if count > 0:
                    await file_input.set_input_files(step.value)
                    return
        except Exception:
            pass
    
    # Fallback 5: Find all visible file inputs and use the first one
    try:
        all_file_inputs = page.locator("input[type='file']")
        count = await all_file_inputs.count()
        if count > 0:
            # Try to find a visible one
            for i in range(count):
                file_input = all_file_inputs.nth(i)
                try:
                    is_visible = await file_input.is_visible()
                    if is_visible:
                        await file_input.set_input_files(step.value)
                        print(f"[info] Found file input using fallback strategy (input {i+1} of {count})")
                        return
                except Exception:
                    continue
            # If no visible one, try the first one anyway
            await all_file_inputs.first.set_input_files(step.value)
            print(f"[info] Found file input using fallback strategy (using first file input)")
            return
    except Exception:
        pass
    
    # If all else fails, raise an error
    raise PlanExecutionError(
        f"Could not find file input with selector '{selector}'. "
        f"Tried the provided selector and multiple fallback strategies."
    )


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
    user_info: Optional[dict] = None,
    filled_fields: Optional[dict[str, str]] = None,
) -> dict[str, str]:
    """Execute the given plan on an already-initialised Playwright page.
    
    Args:
        page: The Playwright page
        plan: The plan to execute
        wait_until: Wait condition for navigation
        user_info: Optional user information for dropdown selection
        filled_fields: Optional dictionary of already-filled fields (selector -> value)
        
    Returns:
        Dictionary of filled fields after execution (selector -> value)
    """
    if filled_fields is None:
        filled_fields = {}
    
    # Filter out steps for already-filled fields
    filtered_steps = []
    for step in plan.steps:
        # Skip fill and select_option steps if the field is already filled
        if step.action in ("fill", "select_option") and step.selector:
            # Check if this field is already filled
            already_filled = False
            for filled_selector, filled_value in filled_fields.items():
                # Check if selectors match (could be exact match or one contains the other)
                if (step.selector == filled_selector or 
                    step.selector in filled_selector or 
                    filled_selector in step.selector):
                    # Check if the value matches
                    if step.value and filled_value:
                        if (step.value.lower() == filled_value.lower() or
                            step.value.lower() in filled_value.lower() or
                            filled_value.lower() in step.value.lower()):
                            print(f"[skip] Skipping {step.action} for '{step.selector}' - already filled with '{filled_value}'")
                            already_filled = True
                            break
                    else:
                        # If field has any value, skip it
                        print(f"[skip] Skipping {step.action} for '{step.selector}' - already has value")
                        already_filled = True
                        break
            
            if already_filled:
                continue
        
        filtered_steps.append(step)
    
    # Execute filtered steps
    for idx, step in enumerate(filtered_steps, start=1):
        # Add 5 second delay before submitting application
        if step.action == "click" and step.selector and (
            "submit" in step.selector.lower() or 
            "submit" in (step.value or "").lower() or
            any(keyword in (step.selector or "").lower() for keyword in ["submit", "application"])
        ):
            print("[info] Waiting 5 seconds before submitting application...")
            await page.wait_for_timeout(5000)
        
        runner = ACTION_RUNNERS.get(step.action)
        if not runner:
            raise PlanExecutionError(f"No runner implemented for action '{step.action}'.")
        print(f"[{idx:02d}] {step.action.upper()} selector={step.selector!r} value={step.value!r}")
        
        # Pass user_info to select handler, others don't need it
        if step.action == "select_option":
            await _handle_select(page, step, wait_until, user_info=user_info)
        else:
            await runner(page, step, wait_until)
        
        # Update filled_fields after executing fill/select actions
        if step.action in ("fill", "select_option") and step.selector:
            try:
                locator = await _ensure_locator(page, step.selector)
                try:
                    value = await locator.input_value()
                    if value and value.strip():
                        filled_fields[step.selector] = value.strip()
                except Exception:
                    # Try text content as fallback
                    try:
                        value = await locator.text_content()
                        if value and value.strip():
                            filled_fields[step.selector] = value.strip()
                    except Exception:
                        pass
            except Exception:
                pass
    
    return filled_fields


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

