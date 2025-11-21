"""Shared OpenAI client initialization for all models."""

import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# Shared OpenAI client instance
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# Export model classes for convenient importing
from models.dropdown_selection_model import DropdownSelectionModel
from models.playwright_plans_model import PlaywrightPlansModel

__all__ = ["client", "DropdownSelectionModel", "PlaywrightPlansModel"]

