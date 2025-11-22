from core.models.client import client
from .config import DEFAULT_MODEL_NAME, DEFAULT_MAX_TOKENS


def generate_text(
    prompt: str, 
    system_prompt: str,
    model: str = DEFAULT_MODEL_NAME, 
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = 0.0
) -> str:
    """
    Generate text using OpenAI ChatCompletion.

    Args:
        prompt: The user prompt describing the task.
        system_prompt: Instructions for the assistant/system.
        model: Model name (default gpt-4).
        max_tokens: Max tokens to generate.
        temperature: Controls randomness (0 = deterministic).

    Returns:
        The generated text from the assistant.
    """
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        max_tokens=max_tokens
    )
    
    return response.choices[0].message.content