import json
from core.models import helpers
from typing import List, Dict, Any


SYSTEM_PROMPT = """
You are a Playwright plan generator for filling out online applications. You are given a JSON array of semantic elements from a webpage.

Your goal is to generate a JSON array of steps that will help a user **fill out an application form and submit it**. Each step should include:

- action: click, fill, select_option
- target: a selector object {type: id/name/aria_label/text, value: string}
- value: optional, for fill/select actions
- notes: optional human-readable explanation

Guidelines:

1. Prioritize filling out forms, selecting options, and clicking submit buttons. Ignore irrelevant buttons or links that do not relate to the application process.
2. Deduplicate steps. Consider elements duplicates if they share the same functional role and the same `id`, `name`, `aria_label`, or visible text. Only include one step per duplicate element.
3. Prefer stable selectors in this order: `id` > `name` > `aria_label` > visible `text`. Use `xpath` **only if no other stable selector is available**.
4. Generate sequential `step_id`s starting from 1.
5. Include metadata: `page_url` if available, `form_id` and `form_name` if applicable.
6. If the page contains **no application forms or actionable steps to progress an application**, return:
```json
{
  "status": "none",
  "steps": [],
  "metadata": {
    "page_url": "string, optional current page"
  }
}
```
7.	Always return a JSON object with this structure:
{
  "status": "success|blocked|none",
  "steps": [
    {
      "step_id": "integer, sequential",
      "action": "click|fill|select_option|wait|navigate",
      "target": {
        "type": "id|name|aria_label|text|xpath",
        "value": "string"
      },
      "value": "optional for fill/select",
      "required": true|false,
      "notes": "optional human-readable explanation"
    }
  ],
  "metadata": {
    "page_url": "string, optional current page",
    "form_id": "string, if known",
    "form_name": "string, if known"
  }
}

Return only JSON, no explanations or extra text.
"""

class PlanBuilderModel():
    def build_plan(self, elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Build a plan for a list of elements.
        """
        prompt = f"Build a plan for the following elements:\n{json.dumps(elements, indent=2)}"
        try:
            result_text = self.call_llm(prompt, SYSTEM_PROMPT)
            # Strip any markdown code blocks if present
            result_text = result_text.strip()
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.startswith("```"):
                result_text = result_text[3:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            result_text = result_text.strip()
            
            # Parse the JSON array response
            results = json.loads(result_text)
            
            return results
        except json.JSONDecodeError as e:
            return [{
                "error": "failed to parse LLM output",
                "raw": result_text,
                "json_error": str(e)
            }]
        except Exception as e:
            return [{
                "error": f"unexpected error: {str(e)}"
            } for element in elements]

    def call_llm(self, prompt: str, system_prompt: str) -> str:
        """
        Helper for subclasses to call the LLM using the shared settings.
        """
        return helpers.generate_text(
            prompt=prompt,
            system_prompt=system_prompt
        )