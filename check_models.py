import urllib.request
import json
import os

def check_models():
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        print("[NOT_CONFIGURED] GOOGLE_API_KEY is required.")
        return

    url = "https://generativelanguage.googleapis.com/v1beta/models"
    request = urllib.request.Request(
        url,
        headers={"x-goog-api-key": key},
    )
    print("Checking models available through the configured Google API key...\n")
    
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode())
            print("Models that support generateContent:")
            for m in data.get("models", []):
                if 'generateContent' in m.get('supportedGenerationMethods', []):
                    print(f"- {m['name'].replace('models/', '')}")
    except Exception as e:
        print(f"[PROVIDER_ERROR] Model check failed: {type(e).__name__}")

if __name__ == "__main__":
    check_models()
