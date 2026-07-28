import base64
import json
import os
import re
import uuid
from datetime import datetime, timezone
from functools import wraps

import requests
from flask import Flask, jsonify, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash

import store
from main import api_key

VISION_MODEL = "google/gemma-3-27b-it:free"
FALLBACK_VISION_MODEL = "nvidia/nemotron-nano-12b-v2-vl:free"

RECIPE_MODEL = "deepseek/deepseek-chat-v3.1:free"
FALLBACK_RECIPE_MODEL = "openai/gpt-oss-20b:free"

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}

PROMPT = (
    "이 이미지는 냉장고 내부 사진이야. 사진에서 식별 가능한 식재료 이름만 "
    '한국어 명사로 뽑아서 JSON 배열로만 답해줘. 예: ["계란", "대파", "두부"]. '
    "다른 설명이나 문장은 붙이지 마."
)

RECIPE_COUNT = 3

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24))

recipe_cache = {}


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "로그인이 필요합니다."}), 401
        return f(*args, **kwargs)

    return wrapper


class ModelResponseError(Exception):
    pass


def extract_content(response):
    response.raise_for_status()
    body = response.json()
    if "error" in body:
        raise ModelResponseError(body["error"].get("message", str(body["error"])))
    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ModelResponseError(f"예상치 못한 응답 형식입니다: {body}") from exc


def call_vision_model(model, image_b64, mime_type):
    return requests.post(
        url="https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{image_b64}"},
                        },
                    ],
                }
            ],
        },
        timeout=30,
    )


def parse_ingredients(text):
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            pass

    cleaned = []
    for item in re.split(r"[,\n]", text):
        item = re.sub(r"^[\s\-\*\d\.\)]+", "", item).strip().strip('"')
        if item:
            cleaned.append(item)
    return cleaned


def analyze_image(image_bytes, mime_type):
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    response = call_vision_model(VISION_MODEL, image_b64, mime_type)
    if response.status_code in (404, 429):
        response = call_vision_model(FALLBACK_VISION_MODEL, image_b64, mime_type)

    content = extract_content(response)
    return parse_ingredients(content)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def build_recipe_prompt(ingredients):
    ingredient_list = ", ".join(ingredients)
    return (
        f"보유 재료: {ingredient_list}. "
        f"이 재료만으로, 또는 최소한의 추가 재료로 만들 수 있는 요리 레시피 {RECIPE_COUNT}개를 추천해줘. "
        "다른 설명 없이 아래 스키마를 정확히 따르는 JSON 배열로만 답해줘:\n"
        '[{"title": "요리 이름", "usedIngredients": ["보유 재료 중 사용한 것"], '
        '"extraIngredients": ["추가로 필요한 재료"], "steps": ["조리 순서 1", "조리 순서 2"], '
        '"cookTimeMinutes": 15, "difficulty": "쉬움|보통|어려움"}]'
    )


def call_text_model(model, prompt):
    return requests.post(
        url="https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=30,
    )


def parse_recipes(text):
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list):
        return None
    return parsed


def generate_recipes(ingredients):
    cache_key = tuple(sorted(i.lower() for i in ingredients))
    if cache_key in recipe_cache:
        return recipe_cache[cache_key]

    prompt = build_recipe_prompt(ingredients)
    response = call_text_model(RECIPE_MODEL, prompt)
    if response.status_code in (404, 429):
        response = call_text_model(FALLBACK_RECIPE_MODEL, prompt)

    content = extract_content(response)
    recipes = parse_recipes(content)

    if recipes is None:
        result = {"recipes": [], "raw": content}
    else:
        result = {"recipes": recipes}

    recipe_cache[cache_key] = result
    return result


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/analyze-image", methods=["POST"])
def api_analyze_image():
    file = request.files.get("image")
    if file is None or file.filename == "":
        return jsonify({"error": "이미지 파일이 필요합니다."}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "jpg, jpeg, png 파일만 지원합니다."}), 400

    ext = file.filename.rsplit(".", 1)[1].lower()
    mime_type = "image/png" if ext == "png" else "image/jpeg"

    try:
        ingredients = analyze_image(file.read(), mime_type)
    except (requests.exceptions.RequestException, ModelResponseError) as exc:
        return jsonify({"error": f"모델 호출 중 오류가 발생했습니다: {exc}"}), 502

    return jsonify({"ingredients": ingredients})


@app.route("/api/generate-recipes", methods=["POST"])
def api_generate_recipes():
    data = request.get_json(silent=True) or {}
    ingredients = data.get("ingredients")
    if not isinstance(ingredients, list) or not ingredients:
        return jsonify({"error": "재료 목록(ingredients 배열)이 필요합니다."}), 400

    ingredients = [str(i).strip() for i in ingredients if str(i).strip()]
    if not ingredients:
        return jsonify({"error": "재료 목록(ingredients 배열)이 필요합니다."}), 400

    try:
        result = generate_recipes(ingredients)
    except (requests.exceptions.RequestException, ModelResponseError) as exc:
        return jsonify({"error": f"모델 호출 중 오류가 발생했습니다: {exc}"}), 502

    return jsonify(result)


@app.route("/api/auth/signup", methods=["POST"])
def api_signup():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    nickname = (data.get("nickname") or "").strip() or email.split("@")[0]

    if not email or not password:
        return jsonify({"error": "이메일과 비밀번호가 필요합니다."}), 400

    users = store.load("users")
    if any(u["email"] == email for u in users):
        return jsonify({"error": "이미 가입된 이메일입니다."}), 400

    user = {
        "id": str(uuid.uuid4()),
        "email": email,
        "password_hash": generate_password_hash(password),
        "nickname": nickname,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    users.append(user)
    store.save("users", users)

    session["user_id"] = user["id"]
    session["nickname"] = user["nickname"]
    return jsonify({"nickname": user["nickname"]}), 201


@app.route("/api/auth/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    users = store.load("users")
    user = next((u for u in users if u["email"] == email), None)
    if user is None or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "이메일 또는 비밀번호가 올바르지 않습니다."}), 401

    session["user_id"] = user["id"]
    session["nickname"] = user["nickname"]
    return jsonify({"nickname": user["nickname"]})


@app.route("/api/auth/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"message": "로그아웃되었습니다."})


@app.route("/api/auth/me")
def api_me():
    if "user_id" not in session:
        return jsonify({"loggedIn": False})
    return jsonify({"loggedIn": True, "nickname": session.get("nickname")})


@app.route("/api/recipes/save", methods=["POST"])
@login_required
def api_save_recipe():
    data = request.get_json(silent=True) or {}
    if not data.get("title"):
        return jsonify({"error": "저장할 레시피 정보가 필요합니다."}), 400

    recipe = {
        "id": str(uuid.uuid4()),
        "user_id": session["user_id"],
        "title": data.get("title", ""),
        "used_ingredients": data.get("usedIngredients", []),
        "extra_ingredients": data.get("extraIngredients", []),
        "steps": data.get("steps", []),
        "cook_time_minutes": data.get("cookTimeMinutes"),
        "difficulty": data.get("difficulty"),
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }

    recipes = store.load("recipes")
    recipes.append(recipe)
    store.save("recipes", recipes)
    return jsonify(recipe), 201


@app.route("/api/recipes/saved", methods=["GET"])
@login_required
def api_list_saved_recipes():
    recipes = store.load("recipes")
    mine = [r for r in recipes if r["user_id"] == session["user_id"]]
    mine.sort(key=lambda r: r["saved_at"], reverse=True)
    return jsonify({"recipes": mine})


@app.route("/api/recipes/saved/<recipe_id>", methods=["DELETE"])
@login_required
def api_delete_saved_recipe(recipe_id):
    recipes = store.load("recipes")
    target = next(
        (r for r in recipes if r["id"] == recipe_id and r["user_id"] == session["user_id"]),
        None,
    )
    if target is None:
        return jsonify({"error": "레시피를 찾을 수 없습니다."}), 404

    recipes = [r for r in recipes if r["id"] != recipe_id]
    store.save("recipes", recipes)
    return "", 204


@app.errorhandler(413)
def file_too_large(_exc):
    return jsonify({"error": "이미지 파일이 너무 큽니다 (최대 10MB)."}), 413


if __name__ == "__main__":
    app.run(debug=True)
