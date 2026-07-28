import os

import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.environ["OPENROUTER_API_KEY"]


def ask(prompt, model="openai/gpt-4o-mini"):
    response = requests.post(
        url="https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


if __name__ == "__main__":
    print(ask("Say hello in one short sentence."))
