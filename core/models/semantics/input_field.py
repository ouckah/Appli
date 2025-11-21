from core.models.semantics.base import BaseSemanticsModel
from typing import List, Dict, Any


SYSTEM_PROMPT = """
You are a semantic analyzer for input fields.
You will be given a list of input fields and you need to generate a semantic representation for each input field.
"""

class InputFieldSemanticsModel(BaseSemanticsModel):
    def generate_semantics(self, elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Generate semantic representations for a list of input fields.

        Args:
            elements (List[Dict[str, Any]]): List of input field dictionaries.

        Returns:
            List[Dict[str, Any]]: List of semantic dictionaries for each input field.
        """
        results = []

        for element in elements:
            prompt = f"Generate a semantic representation for the following input field:\n{json.dumps(element, indent=2)}"
            
            try:
                result_text = self.call_llm(prompt, SYSTEM_PROMPT)
                result_dict = json.loads(result_text)
            except json.JSONDecodeError:
                result_dict = {
                    "error": "failed to parse LLM output",
                    "raw": result_text,
                    "element": element
                }
            except Exception as e:
                result_dict = {
                    "error": f"unexpected error: {str(e)}",
                    "element": element
                }

            results.append(result_dict)

        return results