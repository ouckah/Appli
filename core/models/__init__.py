import os
import openai
from . import semantics


openai.api_key = os.getenv("OPENAI_API_KEY")
DEFAULT_MODEL_NAME = "gpt-4"
DEFAULT_MAX_TOKENS = 3000