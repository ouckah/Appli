import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

SYSTEM_PROMPT = """You are an assistant tasked with drafting job applications.
Use the provided DOM to understand the job listings and craft concise,
tailored responses for each job’s Easy Apply flow."""


def apply_to_jobs(dom_html: str, extra_context: str | None = None) -> str:
    dom_excerpt = dom_html[:100_000]
    messages = [
        {
            "role": "system",
            "content": [
                {"type": "input_text", "text": SYSTEM_PROMPT},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Here is the current page DOM:"},
                {"type": "input_text", "text": dom_excerpt},  # keep prompt manageable
            ],
        },
    ]
    if extra_context:
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Additional instructions:"},
                    {"type": "input_text", "text": extra_context},
                ],
            }
        )

    response = client.responses.create(
        model="gpt-4.1",
        input=messages,
        temperature=0.4,
        max_output_tokens=800,
    )
    return response.output_text

# if __name__ == "__main__":
#     # Example usage: grab the DOM from Playwright or other source first
#     with open("example_job.htm", "r", encoding="utf-8") as f:
#         dom = f.read()

#     result = apply_to_jobs(dom, extra_context="Prioritize remote-friendly roles.")
#     print(result)