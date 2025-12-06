from mcp.server.fastmcp import FastMCP
from tools.actions import open_url, click, fill_input, select_option, close_page, upload_file, check, scroll, submit_form, get_current_url, wait


async def open_url_tool(url: str) -> dict:
    """
    Open a URL in a browser and get a snapshot of the page.
    
    IMPORTANT: After opening a URL, you will receive a page snapshot containing all available
    form fields (inputs, textareas, selects, checkboxes, radios, file_inputs). 
    ONLY fill fields that are present in this snapshot. Do NOT attempt to fill fields that
    are not shown in the snapshot, even if you have that information available.

    Args:
        url: The URL of the page to open. MUST start with http:// NOT https.
    Returns:
        A dictionary containing the page snapshot with all available form fields.
    """
    return await open_url(url)


async def click_tool(selector: str) -> dict:
    """
    Click a button or link in the browser.
    
    IMPORTANT: Only use this tool for buttons or links that are present in the current page snapshot.
    Check the "buttons" or "links" arrays in the page snapshot before attempting to click.
    Do NOT attempt to click elements that don't exist in the snapshot.

    Args:
        selector: The selector of the button or link to click. MUST match a selector from the page snapshot.
    Returns:
        A dictionary containing the updated page snapshot after the click.
    """
    return await click(selector)


async def fill_input_tool(selector: str, value: str) -> dict:
    """
    Fill an input field in the browser.
    
    IMPORTANT: Only use this tool for input fields that are present in the current page snapshot.
    Check the "inputs" array in the page snapshot before attempting to fill a field.
    Do NOT attempt to fill fields that don't exist in the snapshot, even if you have that data available.
    Only fill fields that are explicitly shown in the page snapshot's inputs, textareas, or selects arrays.

    Args:
        selector: The selector of the input field to fill. MUST match a selector from the page snapshot.
        value: The value to fill in the input field.
    Returns:
        A dictionary with success status and the filled element information.
    """
    return await fill_input(selector, value)


async def select_option_tool(selector: str, value: str) -> dict:
    """
    Select an option from a dropdown in the browser.
    
    IMPORTANT: Only use this tool for select/dropdown fields that are present in the current page snapshot.
    Check the "selects" array in the page snapshot before attempting to select an option.
    Do NOT attempt to select options for fields that don't exist in the snapshot.

    Args:
        selector: The selector of the select/dropdown field. MUST match a selector from the page snapshot.
        value: The option value or text to select.
    Returns:
        A dictionary with success status and the selected element information.
    """
    return await select_option(selector, value)


async def close_page_tool() -> dict:
    """
    Close the current page in the browser.
    Use this to close the current page in the browser.
    This is usually at the end of a task or action.
    """
    return await close_page()


async def upload_file_tool(selector: str, file_path: str) -> dict:
    """
    Upload a file to the browser.
    
    IMPORTANT: Only use this tool for file input fields that are present in the current page snapshot.
    Check the "file_inputs" array in the page snapshot before attempting to upload.
    Do NOT attempt to upload to fields that don't exist in the snapshot.

    Args:
        selector: The selector of the file input field. MUST match a selector from the page snapshot.
        file_path: The path to the file to upload.
    Returns:
        A dictionary with success status and the upload element information.
    """
    return await upload_file(selector, file_path)


async def check_tool(selector: str) -> dict:
    """
    Check a checkbox or radio button in the browser.
    
    IMPORTANT: Only use this tool for checkboxes/radios that are present in the current page snapshot.
    Check the "checkboxes" or "radios" arrays in the page snapshot before attempting to check.
    Do NOT attempt to check fields that don't exist in the snapshot.

    Args:
        selector: The selector of the checkbox or radio button. MUST match a selector from the page snapshot.
    Returns:
        A dictionary with success status and the checked element information.
    """
    return await check(selector)


async def scroll_tool(direction: str = "down", amount: int = 500) -> dict:
    """
    Scroll the browser.
    Use this to scroll the browser.
    """
    return await scroll(direction, amount)


async def submit_form_tool(selector: str = None) -> dict:
    """
    Submit a form in the browser.
    Use this to submit a form in the browser.
    """
    return await submit_form(selector)


async def get_current_url_tool() -> str:
    """
    Get the current URL of the browser.
    Use this to get the current URL of the browser.
    """
    return await get_current_url()


async def wait_tool(milliseconds: int) -> dict:
    """
    Wait for a number of milliseconds in the browser.
    Use this to wait for a number of milliseconds in the browser.
    """
    return await wait(milliseconds)


def register_tools(mcp):
    mcp.tool()(open_url_tool)
    mcp.tool()(click_tool)
    mcp.tool()(fill_input_tool)
    mcp.tool()(select_option_tool)
    mcp.tool()(close_page_tool)
    mcp.tool()(upload_file_tool)
    mcp.tool()(check_tool)
    mcp.tool()(scroll_tool)
    mcp.tool()(submit_form_tool)
    mcp.tool()(get_current_url_tool)
    mcp.tool()(wait_tool)