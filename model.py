import os
import os
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

from action_parser import ActionParserError, PlaywrightPlan, parse_playwright_plan

load_dotenv()

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

STRUCTURED_OUTPUT_SPEC = """Return JSON that matches:
{
  "plan": {
    "summary": "High-level description of what will be automated.",
    "status": "pending|confirmed|blocked|error",
    "assumptions": ["list of optional clarifications or TODOs"],
    "steps": [
      {
        "action": "click|fill|select_option|press|check|uncheck|goto|wait_for_selector|wait_for_timeout|upload_file",
        "selector": "Playwright locator or CSS/XPath (omit only for wait_for_timeout)",
        "value": "text to type/option to select/timeout ms/etc (omit if not needed)",
        "reason": "1-line rationale for traceability"
      }
    ]
  }
}"""

SYSTEM_PROMPT = """You are a senior QA automation engineer helping a colleague
write Playwright scripts that automate job applications. Read the provided DOM snapshot,
decide the minimum set of interactions needed to progress the application flow,
and emit a JSON automation plan. Follow these rules:

- Do NOT assume an “Easy Apply” style form; jobs may redirect to another page or portal.
- Consider any clickable elements (links/buttons) that clearly indicate applying to the job, even if no form inputs are present yet.
- Prefer stable selectors (data-* attributes, labels, exact button text) and include fallbacks if relevant.
- Only describe actions present in the DOM excerpt; never hallucinate fields.
- Always include a short reason for each step so humans can audit it.
- Keep plans under 12 steps unless the DOM clearly requires more.
- Respond ONLY with JSON matching the provided schema.
- If the DOM already shows a confirmation/thank-you screen, set status="confirmed" and return an empty steps list.
- If there is no way to progress (e.g., no visible Apply button or link), set status="blocked" and explain in assumptions what is needed.
- Do NOT assume input fields are required if the first actionable step is clicking a link/button.
"""


def generate_playwright_plan(dom_html: str, extra_context: Optional[str] = None) -> PlaywrightPlan:
    dom_excerpt = dom_html[:100_000]
    messages = [
        {
            "role": "system",
            "content": [
                {"type": "input_text", "text": SYSTEM_PROMPT},
                {"type": "input_text", "text": STRUCTURED_OUTPUT_SPEC},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Here is the current page DOM:"},
                {"type": "input_text", "text": dom_excerpt},  # keep prompt manageable
            ],
        },
    ]
    if extra_context:
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Additional instructions:"},
                    {"type": "input_text", "text": extra_context},
                ],
            }
        )

    response = client.responses.create(
        model="gpt-4.1",
        input=messages,
        temperature=0.2,
        max_output_tokens=3000,
    )
    raw_output = response.output_text
    debug = os.getenv("APPLY_DEBUG_LLM_OUTPUT") == "1"
    if debug:
        print("LLM raw output:")
        print(raw_output)
    try:
        return parse_playwright_plan(raw_output)
    except ActionParserError as exc:
        raise ActionParserError(f"{exc}\nRaw LLM output:\n{raw_output}") from exc