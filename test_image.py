import base64
import io

from PIL import Image, ImageDraw

from main import api_key
import requests

IMAGE_MODEL = "nvidia/nemotron-nano-12b-v2-vl:free"


def make_test_image():
    img = Image.new("RGB", (300, 200), color="white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 140, 100], fill="red")
    draw.ellipse([160, 20, 280, 140], fill="blue")
    draw.text((20, 160), "HELLO", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def ask_image(prompt, image_b64, model=IMAGE_MODEL):
    response = requests.post(
        url="https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                        },
                    ],
                }
            ],
        },
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


if __name__ == "__main__":
    b64 = make_test_image()
    result = ask_image(
        "이 이미지에 어떤 도형과 색깔, 텍스트가 있는지 설명해줘.", b64
    )
    print(f"[모델: {IMAGE_MODEL}]")
    print(result)
