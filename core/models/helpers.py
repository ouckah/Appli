from . import DEFAULT_MODEL_NAME, DEFAULT_MAX_TOKENS
import openai


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
    response = openai.ChatCompletion.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        max_tokens=max_tokens
    )
    
    message = response.choices[0].message
    return message.get("content", "").strip() if message else ""