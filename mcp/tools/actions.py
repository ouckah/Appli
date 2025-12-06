import asyncio
from .browser import get_page, close_browser
from playwright.async_api import Page


async def generate_robust_selectors(page: Page, element_handle) -> dict:
    """
    Generate multiple selector strategies for an element.
    Returns a dict with prioritized selectors and element metadata.
    """
    selectors = await element_handle.evaluate("""
        (el) => {
            const result = {
                selectors: [],
                id: null,
                name: null,
                type: null,
                tag: el.tagName.toLowerCase(),
                classes: [],
                dataAttributes: {},
                text: null,
                ariaLabel: null,
                placeholder: null
            };
            
            // ID selector (most reliable)
            if (el.id) {
                result.id = el.id;
                result.selectors.push({ type: 'id', value: `#${el.id}`, priority: 1 });
            }
            
            // Name attribute
            if (el.name) {
                result.name = el.name;
                result.selectors.push({ type: 'name', value: `[name="${el.name}"]`, priority: 2 });
            }
            
            // Type attribute
            if (el.type) {
                result.type = el.type;
            }
            
            // Data attributes
            for (const attr of el.attributes) {
                if (attr.name.startsWith('data-')) {
                    result.dataAttributes[attr.name] = attr.value;
                    result.selectors.push({ 
                        type: 'data-attr', 
                        value: `[${attr.name}="${attr.value}"]`, 
                        priority: 3 
                    });
                }
            }
            
            // Classes
            if (el.className && typeof el.className === 'string') {
                result.classes = el.className.split(' ').filter(c => c.trim());
                if (result.classes.length > 0) {
                    const classSelector = `.${result.classes.join('.')}`;
                    result.selectors.push({ type: 'class', value: classSelector, priority: 4 });
                }
            }
            
            // Text content (for buttons, links)
            const text = el.textContent?.trim();
            if (text && text.length > 0 && text.length < 100) {
                result.text = text;
                result.selectors.push({ type: 'text', value: `text=${text}`, priority: 5 });
            }
            
            // Aria label
            if (el.getAttribute('aria-label')) {
                result.ariaLabel = el.getAttribute('aria-label');
                result.selectors.push({ 
                    type: 'aria-label', 
                    value: `[aria-label="${result.ariaLabel}"]`, 
                    priority: 6 
                });
            }
            
            // Placeholder
            if (el.placeholder) {
                result.placeholder = el.placeholder;
            }
            
            // CSS path as fallback
            const path = [];
            let current = el;
            while (current && current.nodeType === 1) {
                let selector = current.tagName.toLowerCase();
                if (current.id) {
                    selector += `#${current.id}`;
                    path.unshift(selector);
                    break;
                } else {
                    let sibling = current;
                    let nth = 1;
                    while (sibling.previousElementSibling) {
                        sibling = sibling.previousElementSibling;
                        if (sibling.tagName === current.tagName) {
                            nth++;
                        }
                    }
                    if (nth > 1) {
                        selector += `:nth-of-type(${nth})`;
                    }
                }
                path.unshift(selector);
                current = current.parentElement;
            }
            if (path.length > 0) {
                result.selectors.push({ 
                    type: 'css-path', 
                    value: path.join(' > '), 
                    priority: 7 
                });
            }
            
            return result;
        }
    """)
    
    # Sort selectors by priority
    selectors['selectors'].sort(key=lambda x: x['priority'])
    
    return selectors


async def find_associated_label(page: Page, element_handle) -> str:
    """
    Find label text associated with an element.
    Looks for labels in nearby DOM elements (divs, spans, etc.)
    """
    try:
        label_text = await element_handle.evaluate("""
            (el) => {
                // Strategy 1: Look for label element with 'for' attribute
                if (el.id) {
                    const label = document.querySelector(`label[for="${el.id}"]`);
                    if (label) {
                        return label.textContent.trim();
                    }
                }
                
                // Strategy 2a: Check if parent is a label
                let current = el.parentElement;
                while (current && current.tagName !== 'BODY') {
                    if (current.tagName === 'LABEL') {
                        return current.textContent.trim();
                    }
                    current = current.parentElement;
                }
                
                // Strategy 2b: Look for previous siblings with text
                let sibling = el.previousElementSibling;
                while (sibling) {
                    const text = sibling.textContent?.trim();
                    if (text) {
                        // Check if it looks like a label (div/span with text class, or reasonable length)
                        const hasLabelClass = sibling.classList.contains('text') || 
                                            sibling.classList.contains('label') ||
                                            sibling.classList.contains('question');
                        if (hasLabelClass || (text.length > 0 && text.length < 200)) {
                            // Clean up the text (remove required markers, etc.)
                            return text.replace(/[✱*]/g, '').trim();
                        }
                    }
                    sibling = sibling.previousElementSibling;
                }
                
                // Strategy 2c: Check parent's previous siblings
                const parent = el.parentElement;
                if (parent) {
                    sibling = parent.previousElementSibling;
                    if (sibling) {
                        const text = sibling.textContent?.trim();
                        if (text && text.length < 200) {
                            return text.replace(/[✱*]/g, '').trim();
                        }
                    }
                }
                
                // Strategy 2d: Look for aria-label
                if (el.getAttribute('aria-label')) {
                    return el.getAttribute('aria-label').trim();
                }
                
                return null;
            }
        """)
        
        return label_text if label_text else None
        
    except Exception:
        return None


async def get_page_snapshot(page: Page) -> dict:
    """
    Get a comprehensive snapshot of the current page.
    Extracts all interactive elements via DOM queries with robust selectors,
    visual context, and label associations.
    """
    # Wait for page to be ready
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=10000)
    except Exception:
        pass  # Continue even if timeout
    
    # Verify page has loaded by checking for body element
    try:
        body_check = await page.evaluate("() => document.body !== null")
        if not body_check:
            return {
                "url": page.url,
                "error": "Page body not found - page may not have loaded",
                "buttons": [],
                "inputs": [],
                "textareas": [],
                "file_inputs": [],
                "selects": [],
                "checkboxes": [],
                "radios": [],
                "links": []
            }
    except Exception as e:
        return {
            "url": page.url,
            "error": f"Failed to access page DOM: {str(e)}",
            "buttons": [],
            "inputs": [],
            "textareas": [],
            "file_inputs": [],
            "selects": [],
            "checkboxes": [],
            "radios": [],
            "links": []
        }
    
    # Wait for page to be interactive - try waiting for common form elements
    try:
        # Wait for either a button, input, or form to appear (indicates page is interactive)
        await page.wait_for_selector('button, input, form, [role="button"]', timeout=5000, state='attached')
    except Exception:
        pass  # Continue even if no elements found
    
    # Scroll to bottom to ensure all elements are loaded/visible
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await page.wait_for_timeout(2000)  # Wait for any lazy-loaded content
    
    # Scroll back to top
    await page.evaluate("window.scrollTo(0, 0)")
    await page.wait_for_timeout(500)
    
    # Query DOM directly for all interactive elements and collect serializable data
    try:
        elements_data = await page.evaluate("""
            () => {
                const elements = [];
                
                const queryAndAdd = (selector, type) => {
                    try {
                        const nodeList = document.querySelectorAll(selector);
                        nodeList.forEach((el, index) => {
                            try {
                                const rect = el.getBoundingClientRect();
                                const style = window.getComputedStyle(el);
                                // Very lenient visibility check - include all interactive elements
                                // unless they're explicitly hidden with display:none or visibility:hidden
                                const isExplicitlyHidden = style.visibility === 'hidden' || style.display === 'none';
                                // Include all interactive elements regardless of dimensions
                                // (they might be rendered dynamically or have zero size initially)
                                const isVisible = !isExplicitlyHidden;
                            
                                // For select elements, show a sample of options (first 3-5)
                                let text = null;
                                if (type === 'select') {
                                    const options = Array.from(el.options);
                                    if (options.length > 0) {
                                        // Get first 3-5 options as a sample
                                        const sampleSize = Math.min(5, options.length);
                                        const sampleOptions = options.slice(0, sampleSize).map(opt => opt.text?.trim()).filter(t => t);
                                        const remaining = options.length - sampleSize;
                                        
                                        if (sampleOptions.length > 0) {
                                            text = sampleOptions.join(", ");
                                            if (remaining > 0) {
                                                text += `... (${remaining} more options)`;
                                            }
                                        } else {
                                            // Fallback to selected option or placeholder
                                            const selectedOption = el.options[el.selectedIndex];
                                            text = selectedOption ? selectedOption.text?.trim() : null;
                                            if (!text && el.placeholder) {
                                                text = el.placeholder;
                                            }
                                        }
                                    } else if (el.placeholder) {
                                        text = el.placeholder;
                                    }
                                } else {
                                    text = el.textContent?.trim() || null;
                                // Truncate very long text
                                if (text && text.length > 80) {
                                    text = text.substring(0, 77) + "...";
                                }
                                }
                                
                                elements.push({
                                    type: type,
                                    index: index,
                                    id: el.id || null,
                                    name: el.name || null,
                                    value: el.value || null,
                                    checked: el.checked || null,
                                    placeholder: el.placeholder || null,
                                    text: text,
                                    href: el.href || null,
                                    ariaLabel: el.getAttribute('aria-label') || null,
                                    tag: el.tagName.toLowerCase(),
                                    visible: isVisible || (type === 'file'),
                                    selector: selector
                                });
                            } catch (err) {
                                // Skip elements that cause errors
                                console.warn('Error processing element:', err);
                            }
                        });
                    } catch (err) {
                        // Skip selectors that cause errors
                        console.warn('Error with selector ' + selector + ':', err);
                    }
                };
                
                queryAndAdd('button, input[type="button"], input[type="submit"], [role="button"]', 'button');
                queryAndAdd('input[type="text"], input[type="email"], input[type="password"], input[type="tel"], input[type="url"], input[type="search"], input[type="number"], input[type="date"], input[type="time"], input:not([type])', 'textbox');
                queryAndAdd('textarea', 'textarea');
                queryAndAdd('input[type="file"]', 'file');
                queryAndAdd('select, [role="combobox"]', 'select');
                queryAndAdd('input[type="checkbox"]', 'checkbox');
                queryAndAdd('input[type="radio"]', 'radio');
                queryAndAdd('a[href]', 'link');
                
                // Also try to find contenteditable divs and custom input-like elements
                queryAndAdd('[contenteditable="true"]', 'textbox');
                queryAndAdd('div[role="textbox"], div[role="combobox"]', 'textbox');
                
                return elements;
            }
        """)
    except Exception as e:
        # If evaluation fails, return empty snapshot with error info
        return {
            "url": page.url,
            "error": f"Failed to extract elements: {str(e)}",
            "buttons": [],
            "inputs": [],
            "textareas": [],
            "file_inputs": [],
            "selects": [],
            "checkboxes": [],
            "radios": [],
            "links": []
        }
    
    # Check if we got any elements
    if not elements_data:
        return {
            "url": page.url,
            "error": "No elements found on page",
            "buttons": [],
            "inputs": [],
            "textareas": [],
            "file_inputs": [],
            "selects": [],
            "checkboxes": [],
            "radios": [],
            "links": []
        }
    
    # Enhance each element with robust selectors and labels
    enhanced_elements = {
        "buttons": [],
        "inputs": [],
        "textareas": [],
        "file_inputs": [],
        "selects": [],
        "checkboxes": [],
        "radios": [],
        "links": []
    }
    
    for elem_data in elements_data:
        # Skip only explicitly hidden elements (visibility: hidden or display: none)
        # Include all interactive elements - visibility check already done in JS
        # (we only exclude elements with display:none or visibility:hidden)
        
        # Generate selectors directly from collected data (more reliable than re-querying)
        selectors = []
        primary_selector = None
        
        # Priority 1: ID selector (most reliable)
        if elem_data['id']:
            primary_selector = f"#{elem_data['id']}"
            selectors.append({'type': 'id', 'value': primary_selector, 'priority': 1})
        
        # Priority 2: Name attribute
        if elem_data['name']:
            name_selector = f"[name='{elem_data['name']}']"
            if not primary_selector:
                primary_selector = name_selector
            selectors.append({'type': 'name', 'value': name_selector, 'priority': 2})
        
        # Priority 3: Class selector (only if simple)
        if elem_data.get('className'):
            classes = [c.strip() for c in elem_data['className'].split(' ') if c.strip()][:2]  # Limit to 2 classes
            if classes:
                class_selector = f".{'.'.join(classes)}"
                if not primary_selector:
                    primary_selector = class_selector
                selectors.append({'type': 'class', 'value': class_selector, 'priority': 3})
        
        # Priority 4: Text selector (for buttons, links) - only if short
        if elem_data.get('text') and len(elem_data['text']) < 50:
            text_selector = f"text={elem_data['text']}"
            if not primary_selector:
                primary_selector = text_selector
            selectors.append({'type': 'text', 'value': text_selector, 'priority': 4})
        
        # Priority 5: Aria label
        if elem_data.get('ariaLabel'):
            aria_selector = f"[aria-label='{elem_data['ariaLabel']}']"
            if not primary_selector:
                primary_selector = aria_selector
            selectors.append({'type': 'aria-label', 'value': aria_selector, 'priority': 5})
        
        # Fallback: Use tag + index if we have no other selector
        if not primary_selector:
            primary_selector = f"{elem_data['tag']}:nth-of-type({elem_data['index'] + 1})"
        
        # Try to find label using element handle if possible, otherwise skip label
        label_text = None
        try:
            # Try to get element handle for label finding
            element_handle = None
            if elem_data['id']:
                element_handle = await page.query_selector(f"#{elem_data['id']}")
            elif elem_data['name']:
                all_by_name = await page.query_selector_all(f"[name='{elem_data['name']}']")
                if all_by_name:
                    element_handle = all_by_name[0]
            
            if element_handle:
                label_text = await find_associated_label(page, element_handle)
        except:
            pass  # Label finding is optional
        
        try:
            # Build concise element representation
            # For selects, text now contains a sample of options (first 5)
            name = elem_data.get('text') or elem_data.get('ariaLabel') or elem_data.get('name') or elem_data.get('placeholder')
            
            # Build context string - keep it short but informative
            if label_text:
                # If we have a label, combine with name/options sample
                if name and name != label_text:
                    # For selects, show label with option sample (truncated)
                    if elem_data['type'] == 'select':
                        opt_text = name[:40] + "..." if len(name) > 40 else name
                        context = f"{label_text} ({opt_text})"
                    else:
                        # For other elements, keep it shorter
                        if len(name) < 30:
                            context = f"{label_text}: {name}"
                        else:
                            context = label_text
                else:
                    context = label_text
            elif name:
                # For selects, the name is already a sample, so show it (truncated)
                if elem_data['type'] == 'select':
                    opt_text = name[:40] + "..." if len(name) > 40 else name
                    context = f"Select: {opt_text}"
                else:
                    # Truncate long names
                    if len(name) > 60:
                        context = name[:57] + "..."
                    else:
                        context = name
            else:
                context = primary_selector or elem_data['type']
            
            enhanced = {
                "selector": primary_selector,
                "context": context,
            }
            
            # Only add value/checked/placeholder if they exist and are meaningful
            if elem_data.get('value'):
                enhanced["value"] = elem_data['value']
            if elem_data.get('checked') is not None:
                enhanced["checked"] = elem_data['checked']
            if elem_data.get('placeholder'):
                enhanced["placeholder"] = elem_data['placeholder']
            if elem_data.get('href'):
                enhanced["href"] = elem_data['href']
            
            # Categorize
            if elem_data['type'] == 'button':
                enhanced_elements['buttons'].append(enhanced)
            elif elem_data['type'] == 'textbox':
                enhanced_elements['inputs'].append(enhanced)
            elif elem_data['type'] == 'textarea':
                enhanced_elements['textareas'].append(enhanced)
            elif elem_data['type'] == 'file':
                enhanced_elements['file_inputs'].append(enhanced)
            elif elem_data['type'] == 'select':
                enhanced_elements['selects'].append(enhanced)
            elif elem_data['type'] == 'checkbox':
                enhanced_elements['checkboxes'].append(enhanced)
            elif elem_data['type'] == 'radio':
                enhanced_elements['radios'].append(enhanced)
            elif elem_data['type'] == 'link':
                enhanced_elements['links'].append(enhanced)
        except Exception as e:
                # If enhancement fails, skip this element
                continue
    
    # Deduplicate elements by selector and limit counts
    def deduplicate_and_limit(items, max_items=50):
        seen_selectors = set()
        unique_items = []
        for item in items:
            selector = item.get('selector')
            if selector and selector not in seen_selectors:
                seen_selectors.add(selector)
                unique_items.append(item)
                if len(unique_items) >= max_items:
                    break
        return unique_items
    
    # Deduplicate and limit each category (reduced limits for conciseness)
    result = {
        "url": page.url,
        "buttons": deduplicate_and_limit(enhanced_elements['buttons'], 15),
        "inputs": deduplicate_and_limit(enhanced_elements['inputs'], 20),
        "textareas": deduplicate_and_limit(enhanced_elements['textareas'], 5),
        "file_inputs": deduplicate_and_limit(enhanced_elements['file_inputs'], 5),
        "selects": deduplicate_and_limit(enhanced_elements['selects'], 10),
        "checkboxes": deduplicate_and_limit(enhanced_elements['checkboxes'], 10),
        "radios": deduplicate_and_limit(enhanced_elements['radios'], 10),
        "links": deduplicate_and_limit(enhanced_elements['links'], 15),
    }
    
    return result


async def open_url(url: str) -> dict:
    page = await get_page()


    # Wait for page to load - use load for faster response, fallback to networkidle for SPAs
    try:
        await page.goto(url, wait_until="load", timeout=15000)
    except Exception:
        # Fallback to networkidle if load times out (for SPAs)
        try:
            await page.goto(url, wait_until="networkidle", timeout=20000)
        except Exception:
            # If both fail, still try to continue
            pass
    
    # For SPAs, wait for the React app to actually render content
    # The root div might exist but be empty - we need to wait for it to have children
    try:
        await page.wait_for_function(
            """
            () => {
                // Check if we have actual interactive elements
                const interactiveCount = document.querySelectorAll('button, input, form, select, textarea, [role="button"], [role="textbox"], [contenteditable]').length;
                if (interactiveCount > 0) {
                    return true;
                }
                
                // Check if React root has actual content (not just styles)
                const root = document.querySelector('[id*="root"], [id*="app"], [id*="main"]');
                if (root) {
                    // Root should have children that aren't just style tags
                    const children = Array.from(root.children);
                    const hasContent = children.some(child => 
                        child.tagName !== 'STYLE' && 
                        child.tagName !== 'SCRIPT' &&
                        (child.children.length > 0 || child.textContent.trim().length > 0)
                    );
                    if (hasContent) {
                        return true;
                    }
                }
                
                // Check if body has substantial content beyond noscript
                const bodyText = document.body ? document.body.textContent.trim() : '';
                const noscript = document.querySelector('noscript');
                const noscriptText = noscript ? noscript.textContent : '';
                const bodyWithoutNoscript = bodyText.replace(noscriptText, '').trim();
                
                return bodyWithoutNoscript.length > 200;
            }
            """,
            timeout=10000
        )
    except Exception:
        # If that fails, wait longer - React apps can be slow to hydrate
        pass
    
    # Wait for all scripts to finish executing
    try:
        await page.wait_for_load_state("domcontentloaded")
        # Wait for all scripts to be ready
        await page.evaluate("""
            () => {
                return new Promise((resolve) => {
                    if (document.readyState === 'complete') {
                        resolve();
                    } else {
                        window.addEventListener('load', resolve, { once: true });
                        // Timeout after 10 seconds
                        setTimeout(resolve, 10000);
                    }
                });
            }
        """)
    except Exception:
        pass
    
    # Additional wait for React hydration and dynamic content
    # Some React apps need extra time after initial render
    await page.wait_for_timeout(2000)
    
    # Try scrolling to trigger lazy loading
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await page.wait_for_timeout(500)
    await page.evaluate("window.scrollTo(0, 0)")
    await page.wait_for_timeout(500)
    
    result = await get_page_snapshot(page)
    return result


async def resolve_selector(page: Page, selector: str):
    """
    Resolve a selector string to a locator, trying multiple strategies.
    Handles both new format (from snapshot) and legacy text= format.
    """
    # Handle text selectors (legacy format)
    if selector.startswith("text="):
        text = selector[5:]
        return page.get_by_text(text, exact=False).first
    
    # Handle new selector format - try in order of priority
    # If selector is a dict/list from snapshot, extract the primary selector
    if isinstance(selector, dict) and 'selectors' in selector:
        selectors = selector['selectors']
    elif isinstance(selector, list):
        selectors = selector
    else:
        # Direct selector string
        return page.locator(selector).first
    
    # Try each selector in priority order
    last_error = None
    for sel_info in selectors:
        try:
            sel_value = sel_info['value'] if isinstance(sel_info, dict) else sel_info
            if sel_value.startswith("text="):
                text = sel_value[5:]
                locator = page.get_by_text(text, exact=False).first
            else:
                locator = page.locator(sel_value).first
            
            # Verify it exists
            if await locator.count() > 0:
                return locator
        except Exception as e:
            last_error = e
            continue
    
    # If all selectors failed, try the primary selector as fallback
    if isinstance(selector, dict) and 'primary_selector' in selector:
        return page.locator(selector['primary_selector']).first
    
    # Final fallback: use selector as-is
    return page.locator(selector).first


async def click(selector: str) -> dict:
    page = await get_page()
    
    locator = await resolve_selector(page, selector)
    
    # Try normal click first, fallback to JS click if hidden
    new_page = None
    try:
        await locator.wait_for(state="visible", timeout=2000)
        # Check if click opens a new page/tab
        async with page.context.expect_page(timeout=3000) as new_page_info:
            await locator.click()
        new_page = await new_page_info.value
    except:
        # No new page, try regular click or JS click
        try:
            await locator.click()
        except:
            await locator.evaluate("el => el.click()")
    
    # Use new page if one was opened, otherwise use current page
    target_page = new_page if new_page else page
    
    # Wait for page to settle
    await target_page.wait_for_timeout(2000)
    
    await page.wait_for_timeout(1000)
    
    return await get_page_snapshot(target_page)


async def fill_input(selector: str, value: str) -> dict:
    page = await get_page()
    locator = await resolve_selector(page, selector)

    # Check if this is an autocomplete/combobox input
    is_autocomplete = await locator.evaluate("""
        (el) => {
            // Check for autocomplete indicators
            const hasList = el.hasAttribute('list');
            const hasAriaAutocomplete = el.getAttribute('aria-autocomplete') === 'list' || 
                                        el.getAttribute('aria-autocomplete') === 'both';
            const hasRole = el.getAttribute('role') === 'combobox';
            const hasAutocompleteClass = el.className && (
                el.className.includes('autocomplete') || 
                el.className.includes('combobox') ||
                el.className.includes('typeahead')
            );
            
            return hasList || hasAriaAutocomplete || hasRole || hasAutocompleteClass;
        }
    """)
    
    if is_autocomplete:
        # For autocomplete inputs, use type + arrow down + enter strategy
        await locator.click()  # Focus the input
        await locator.fill("")  # Clear any existing value
        await locator.type(value, delay=100)  # Type the value with delay to trigger dropdown
        
        # Wait for dropdown to appear - check for common dropdown indicators
        dropdown_appeared = False
        for _ in range(10):  # Wait up to 2 seconds (10 * 200ms)
            await page.wait_for_timeout(200)
            # Check if dropdown/options are visible
            has_dropdown = await page.evaluate("""
                () => {
                    // Check for common dropdown indicators
                    const dropdowns = document.querySelectorAll('[role="listbox"], .dropdown-menu, .autocomplete-options, [class*="dropdown"], [class*="suggestions"], [class*="options"]');
                    for (let dd of dropdowns) {
                        const style = window.getComputedStyle(dd);
                        if (style.display !== 'none' && style.visibility !== 'hidden') {
                            return true;
                        }
                    }
                    return false;
                }
            """)
            if has_dropdown:
                dropdown_appeared = True
                break
        
        # If no dropdown detected, wait a bit more (might be loading)
        if not dropdown_appeared:
            await page.wait_for_timeout(1000)
        
        # Select first option
        await locator.press("ArrowDown")
        await page.wait_for_timeout(300)
        await locator.press("Enter")
    else:
        # Normal fill for regular inputs
        await locator.fill(value)
        
        # Fallback: Check if value was actually set, if not try autocomplete strategy
        actual_value = await locator.input_value()
        if actual_value != value:
            # Value wasn't set correctly, might be an autocomplete - try dropdown strategy
            await locator.click()  # Focus the input
            await locator.fill("")  # Clear any existing value
            await locator.type(value, delay=100)  # Type the value with delay to trigger dropdown
            
            # Wait for dropdown to appear
            dropdown_appeared = False
            for _ in range(10):  # Wait up to 2 seconds
                await page.wait_for_timeout(200)
                has_dropdown = await page.evaluate("""
                    () => {
                        const dropdowns = document.querySelectorAll('[role="listbox"], .dropdown-menu, .autocomplete-options, [class*="dropdown"], [class*="suggestions"], [class*="options"]');
                        for (let dd of dropdowns) {
                            const style = window.getComputedStyle(dd);
                            if (style.display !== 'none' && style.visibility !== 'hidden') {
                                return true;
                            }
                        }
                        return false;
                    }
                """)
                if has_dropdown:
                    dropdown_appeared = True
                    break
            
            if not dropdown_appeared:
                await page.wait_for_timeout(1000)
            
            await locator.press("ArrowDown")
            await page.wait_for_timeout(300)
            await locator.press("Enter")
    
    # Get the filled element's info
    element_info = await locator.evaluate("""
        (el) => {
            return {
                type: el.type || null,
                id: el.id || null,
                name: el.name || null,
                value: el.value || null,
                placeholder: el.placeholder || null,
                ariaLabel: el.getAttribute('aria-label') || null,
                tag: el.tagName.toLowerCase(),
                className: el.className || null
            };
        }
    """)
    
    # Generate selectors
    selectors = []
    primary_selector = None
    
    if element_info['id']:
        primary_selector = f"#{element_info['id']}"
        selectors.append({'type': 'id', 'value': primary_selector, 'priority': 1})
    
    if element_info['name']:
        name_selector = f"[name='{element_info['name']}']"
        if not primary_selector:
            primary_selector = name_selector
        selectors.append({'type': 'name', 'value': name_selector, 'priority': 2})
    
    if element_info.get('className'):
        classes = [c.strip() for c in element_info['className'].split(' ') if c.strip()][:2]
        if classes:
            class_selector = f".{'.'.join(classes)}"
            if not primary_selector:
                primary_selector = class_selector
            selectors.append({'type': 'class', 'value': class_selector, 'priority': 3})
    
    if element_info.get('ariaLabel'):
        aria_selector = f"[aria-label='{element_info['ariaLabel']}']"
        if not primary_selector:
            primary_selector = aria_selector
        selectors.append({'type': 'aria-label', 'value': aria_selector, 'priority': 5})
    
    if not primary_selector:
        primary_selector = selector
    
    # Find associated label
    label_text = None
    try:
        # Try to get element handle for label finding
        element_handle = None
        if element_info['id']:
            element_handle = await page.query_selector(f"#{element_info['id']}")
        elif element_info['name']:
            all_by_name = await page.query_selector_all(f"[name='{element_info['name']}']")
            if all_by_name:
                element_handle = all_by_name[0]
        
        if element_handle:
            label_text = await find_associated_label(page, element_handle)
    except Exception:
        pass
    
    return {
        "success": True,
        "element": {
            "type": element_info['type'] or 'textbox',
            "tag": element_info['tag'],
            "id": element_info['id'],
            "name": element_info['name'],
            "value": element_info['value'],
            "placeholder": element_info['placeholder'],
            "ariaLabel": element_info['ariaLabel'],
            "label": label_text,
            "selector": primary_selector,
            "selectors": selectors
        }
    }


async def select_option(selector: str, value: str) -> dict:
    page = await get_page()
    locator = await resolve_selector(page, selector)

    # For large dropdowns, use JavaScript for better performance
    # Try multiple matching strategies
    success = await locator.evaluate("""
        (select, searchValue) => {
            const options = Array.from(select.options);
            const searchLower = searchValue.toLowerCase().trim();
            
            // Strategy 1: Exact match (case-insensitive)
            for (let i = 0; i < options.length; i++) {
                const optionText = options[i].text?.trim() || '';
                if (optionText.toLowerCase() === searchLower) {
                    select.selectedIndex = i;
                    select.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                }
            }
            
            // Strategy 2: Starts with match
            for (let i = 0; i < options.length; i++) {
                const optionText = options[i].text?.trim() || '';
                if (optionText.toLowerCase().startsWith(searchLower)) {
                    select.selectedIndex = i;
                    select.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                }
            }
            
            // Strategy 3: Contains match (split search value into words)
            const searchWords = searchLower.split(/[\\s,]+/).filter(w => w.length > 2);
            if (searchWords.length > 0) {
                for (let i = 0; i < options.length; i++) {
                    const optionText = options[i].text?.trim().toLowerCase() || '';
                    // Check if all significant words are present
                    const allWordsPresent = searchWords.every(word => optionText.includes(word));
                    if (allWordsPresent) {
                        select.selectedIndex = i;
                        select.dispatchEvent(new Event('change', { bubbles: true }));
                        return true;
                    }
                }
            }
            
            // Strategy 4: Value attribute match
            for (let i = 0; i < options.length; i++) {
                if (options[i].value && options[i].value.toLowerCase().includes(searchLower)) {
                    select.selectedIndex = i;
                    select.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                }
            }
            
            return false;
        }
    """, value)
    
    if not success:
        # Fallback to Playwright's select_option (might timeout on large dropdowns)
        try:
            await locator.select_option(value, timeout=5000)
        except:
            # Last resort: try with label matching
            await locator.select_option(label=value, timeout=5000)
    
    return await get_page_snapshot(page)


async def upload_file(selector: str, file_path: str) -> dict:
    page = await get_page()
    locator = await resolve_selector(page, selector)

    await locator.set_input_files(file_path)
    return await get_page_snapshot(page)


async def check(selector: str) -> dict:
    page = await get_page()
    locator = await resolve_selector(page, selector)

    # Try normal check first
    try:
        await locator.check(timeout=5000)
    except Exception:
        # If normal check fails (e.g., blocked by captcha iframe), use JavaScript fallback
        await locator.evaluate("""
            (el) => {
                if (el.type === 'checkbox' || el.type === 'radio') {
                    el.checked = true;
                    // Trigger change event for any listeners
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    el.dispatchEvent(new Event('click', { bubbles: true }));
                }
            }
        """)
    
    # Get the checked element's info
    element_info = await locator.evaluate("""
        (el) => {
            return {
                type: el.type || null,
                id: el.id || null,
                name: el.name || null,
                value: el.value || null,
                checked: el.checked || false,
                ariaLabel: el.getAttribute('aria-label') || null,
                tag: el.tagName.toLowerCase(),
                className: el.className || null
            };
        }
    """)
    
    # Generate selectors
    selectors = []
    primary_selector = None
    
    if element_info['id']:
        primary_selector = f"#{element_info['id']}"
        selectors.append({'type': 'id', 'value': primary_selector, 'priority': 1})
    
    if element_info['name']:
        name_selector = f"[name='{element_info['name']}']"
        if not primary_selector:
            primary_selector = name_selector
        selectors.append({'type': 'name', 'value': name_selector, 'priority': 2})
    
    if element_info.get('className'):
        classes = [c.strip() for c in element_info['className'].split(' ') if c.strip()][:2]
        if classes:
            class_selector = f".{'.'.join(classes)}"
            if not primary_selector:
                primary_selector = class_selector
            selectors.append({'type': 'class', 'value': class_selector, 'priority': 3})
    
    if element_info.get('ariaLabel'):
        aria_selector = f"[aria-label='{element_info['ariaLabel']}']"
        if not primary_selector:
            primary_selector = aria_selector
        selectors.append({'type': 'aria-label', 'value': aria_selector, 'priority': 5})
    
    if not primary_selector:
        primary_selector = selector
    
    # Find associated label
    label_text = None
    try:
        element_handle = None
        if element_info['id']:
            element_handle = await page.query_selector(f"#{element_info['id']}")
        elif element_info['name']:
            all_by_name = await page.query_selector_all(f"[name='{element_info['name']}']")
            if all_by_name:
                element_handle = all_by_name[0]
        
        if element_handle:
            label_text = await find_associated_label(page, element_handle)
    except Exception:
        pass
    
    return {
        "success": True,
        "element": {
            "type": element_info['type'] or 'checkbox',
            "tag": element_info['tag'],
            "id": element_info['id'],
            "name": element_info['name'],
            "value": element_info['value'],
            "checked": element_info['checked'],
            "ariaLabel": element_info['ariaLabel'],
            "label": label_text,
            "selector": primary_selector,
            "selectors": selectors
        }
    }


async def scroll(direction: str = "down", amount: int = 500) -> dict:
    page = await get_page()
    if direction == "down":
        await page.evaluate(f"window.scrollBy(0, {amount})")
    elif direction == "up":
        await page.evaluate(f"window.scrollBy(0, -{amount})")
    else:
        raise ValueError(f"Invalid direction: {direction}")
    return await get_page_snapshot(page)


async def submit_form(selector: str = None) -> dict:
    page = await get_page()
    if selector:
        await page.locator(selector).first.click()
    else:
        await page.locator("form").first.submit()
    return await get_page_snapshot(page)


async def get_current_url() -> str:
    page = await get_page()
    return page.url


async def wait(milliseconds: int) -> dict:
    page = await get_page()
    await page.wait_for_timeout(milliseconds)
    return await get_page_snapshot(page)


async def close_page():
    await close_browser()