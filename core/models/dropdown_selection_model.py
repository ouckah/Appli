"""Model for intelligently selecting dropdown options using LLM reasoning."""

import json
from typing import Optional

from models import client


class DropdownSelectionModel:
    """Model for intelligently selecting dropdown options using LLM reasoning."""
    
    def __init__(self):
        """Initialize the DropdownSelectionModel with the shared OpenAI client."""
        self.client = client

    def select_best_option(
        self,
        field_name: str,
        target_value: str,
        available_options: list[str],
        user_info: Optional[dict] = None,
    ) -> Optional[str]:
        """Use LLM to intelligently select the best option from a dropdown given user context.
        
        Args:
            field_name: The name/label of the dropdown field (e.g., "School", "Ethnicity")
            target_value: The desired value to select (e.g., "Rutgers University", "Prefer not to say")
            available_options: List of all available options in the dropdown
            user_info: Optional dictionary of user information for context
            
        Returns:
            The best matching option text, or None if no good match found
        """
        if not available_options:
            return None
        
        # If only one option, return it
        if len(available_options) == 1:
            return available_options[0]
        
        # Build context about the user
        user_context = ""
        if user_info:
            user_context = f"\n\nUser information for context:\n{json.dumps(user_info, indent=2)}"
        
        prompt = f"""You are helping select the best option from a dropdown menu for a job application form.

Field: {field_name}
Desired value: {target_value}
Available options:
{chr(10).join(f"- {opt}" for opt in available_options)}{user_context}

Select the option that best matches the desired value. Consider:
- Exact matches are preferred
- Semantic equivalence (e.g., "prefer not to say" = "decline to self verify")
- Context from user information when relevant
- If no good match exists, return "OTHER" if available, otherwise return the closest match

Respond with ONLY the exact option text from the list above, nothing else."""
        
        messages = [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            }
        ]
        
        try:
            response = self.client.responses.create(
                model="gpt-4.1",
                input=messages,
                temperature=0.1,  # Low temperature for consistent selection
                max_output_tokens=200,
            )
            selected_option = response.output_text.strip()
            
            # Verify the selected option is in the available options
            # Try exact match first
            if selected_option in available_options:
                return selected_option
            
            # Try case-insensitive match
            selected_lower = selected_option.lower()
            for option in available_options:
                if option.lower() == selected_lower:
                    return option
            
            # Try partial match (in case LLM returned a variation)
            for option in available_options:
                if selected_lower in option.lower() or option.lower() in selected_lower:
                    return option
            
            # If no match found, return None (fallback to fuzzy matching)
            print(f"[warn] LLM selected '{selected_option}' which doesn't match any available option")
            return None
            
        except Exception as e:
            print(f"[warn] LLM option selection failed: {e}, falling back to fuzzy matching")
            return None

