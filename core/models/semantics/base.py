from abc import ABC, abstractmethod
from typing import List, Dict, Any
import core.models.helpers as helpers


class BaseSemanticsModel(ABC):
    """
    Base class for extracting semantics from parsed HTML elements.
    Subclasses implement generate_semantics for specific element types (InputField, Button, Select, Label).
    """
    def __init__(self, model: str = helpers.DEFAULT_MODEL_NAME, max_tokens: int = helpers.DEFAULT_MAX_TOKENS):
        self.model = model
        self.max_tokens = max_tokens

    @abstractmethod
    def generate_semantics(self, elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Generate semantic representation for a list of parsed HTML elements.
        
        Args:
            elements: A list of dictionaries representing parsed HTML elements.
        
        Returns:
            A list of dictionaries representing structured semantics.
        """
        pass

    def call_llm(self, prompt: str, system_prompt: str) -> str:
        """
        Helper for subclasses to call the LLM using the shared settings.
        """
        return helpers.generate_text(
            prompt=prompt,
            system_prompt=system_prompt,
            model=self.model,
            max_tokens=self.max_tokens
        )