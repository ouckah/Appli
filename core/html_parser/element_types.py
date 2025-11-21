from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Option:
    """Represents a single dropdown option or radio/checkbox choice."""
    value: str
    label: str
    selected: bool = False

@dataclass
class InputField:
    """Represents an input field (text, email, password, etc.)."""
    id: Optional[str] = None
    name: Optional[str] = None
    type: str = "text"
    placeholder: Optional[str] = None
    required: bool = False
    value: Optional[str] = None
    aria_label: Optional[str] = None
    aria_describedby: Optional[str] = None

@dataclass
class Button:
    """Represents a clickable button."""
    id: Optional[str] = None
    name: Optional[str] = None
    text: Optional[str] = None
    type: str = "button"   # "submit", "reset", etc.
    disabled: bool = False

@dataclass
class Label:
    """Represents a label for an input field."""
    id: Optional[str] = None
    for_id: Optional[str] = None
    text: Optional[str] = None

@dataclass
class Select:
    id: Optional[str] = None
    name: Optional[str] = None
    options: List[Option] = field(default_factory=list)
    required: bool = False

@dataclass
class Form:
    """Represents a full form with inputs, buttons, and select options."""
    id: Optional[str] = None
    name: Optional[str] = None
    action: Optional[str] = None
    method: str = "GET"
    inputs: List[InputField] = field(default_factory=list)
    buttons: List[Button] = field(default_factory=list)
    selects: List[Select] = field(default_factory=list)
    labels: List[Label] = field(default_factory=list)