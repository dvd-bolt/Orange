import urllib.request
import json
import os

def check_models():
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        print("Ключ не найден!")
        return

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
    print("Стучимся в Google API...\n")
    
    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode())
            print("Живые модели, доступные для генерации текста:")
            for m in data.get("models", []):
                # Фильтруем только те, что умеют генерировать текст
                if 'generateContent' in m.get('supportedGenerationMethods', []):
                    print(f"- {m['name'].replace('models/', '')}")
    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    check_models()