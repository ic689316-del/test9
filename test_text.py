from main import ask

TEXT_MODEL = "openai/gpt-oss-20b:free"

if __name__ == "__main__":
    result = ask("한국의 수도는 어디야? 한 문장으로 답해줘.", model=TEXT_MODEL)
    print(f"[모델: {TEXT_MODEL}]")
    print(result)
