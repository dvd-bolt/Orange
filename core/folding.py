import os
import httpx

async def summarize_text(text: str, api_key: str) -> str:
    """Calls Gemini Flash Lite to generate a dense bullet-point summary of the text."""
    model_name = os.environ.get("ORANGE_LITE_MODEL", "google:gemini-3.5-flash-lite").split(":")[-1]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key
    }
    prompt = (
        "Суммаризируй следующую историю переписки в краткий, плотный список ключевых тезисов и фактов на русском языке. "
        "Обязательно сохрани все важные пути к файлам, выводы, имена и ключевые числовые значения:\n\n"
        f"{text}"
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(url, headers=headers, json=body)
        response.raise_for_status()
        data = response.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError):
            return "Не удалось сжать историю."
