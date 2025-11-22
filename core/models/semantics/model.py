import json
from core.models import helpers
from typing import List, Dict, Any


SYSTEM_PROMPT = """
You are a semantic analyzer for interactable elements on a webpage.
You will be given a list of HTML elements which could be buttons, inputs, selects, or other interactable elements.

For each element:
1. Determine its **functional role** (e.g., Button, Input Field, Dropdown, Checkbox, Label, Link).
2. Generate a semantic JSON object that best represents the element’s behavior and metadata.
3. Include as much metadata as possible:
   - id
   - name
   - type (for inputs or buttons)
   - element_type (HTML tag type)
   - form_id (if part of a form)
   - aria_label (if present)
4. Do NOT include the HTML code of the element in the output.
5. For buttons, include button_type (Submit, Reset, Regular, etc.)
6. For inputs, include input_type (text, hidden, checkbox, etc.)
7. For selects, include the list of options with value/text/selected.

Return a JSON array, one object per element, without any additional text. Ensure the JSON schema reflects the **actual role and function** of the element, not just its HTML tag.
"""

class SemanticsModel():
    def generate_semantics(self, elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Generate semantic representations for a list of input fields.
        Processes all elements in a single batch API call to reduce costs.

        Args:
            elements (List[Dict[str, Any]]): List of input field dictionaries.

        Returns:
            List[Dict[str, Any]]: List of semantic dictionaries for each input field.
        """
        # If no elements, return empty list
        if not elements:
            return []

        # Batch process all elements in a single API call
        prompt = f"Generate semantic representations for the following interactable elements:\n{json.dumps(elements, indent=2)}"
        
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
            
            # Ensure we return a list and match the number of input elements
            if not isinstance(results, list):
                results = [results]
            
            # If we got fewer results than inputs, pad with errors
            while len(results) < len(elements):
                results.append({
                    "error": "missing result from LLM",
                    "element": elements[len(results)]
                })
            
            # If we got more results than inputs, truncate
            return results[:len(elements)]
            
        except json.JSONDecodeError as e:
            # If parsing fails, return errors for all elements
            return [{
                "error": "failed to parse LLM output",
                "raw": result_text,
                "element": element,
                "json_error": str(e)
            } for element in elements]
        except Exception as e:
            # If API call fails, return errors for all elements
            return [{
                "error": f"unexpected error: {str(e)}",
                "element": element
            } for element in elements]


    def call_llm(self, prompt: str, system_prompt: str) -> str:
        """
        Helper for subclasses to call the LLM using the shared settings.
        """
        return helpers.generate_text(
            prompt=prompt,
            system_prompt=system_prompt
        )