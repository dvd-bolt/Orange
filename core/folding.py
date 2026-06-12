import os
import httpx
from typing import List, Dict, Any

def count_tokens(text: str) -> int:
    """Approximates token count based on average word length."""
    if not text:
        return 0
    return len(text.split()) * 4 // 3

async def summarize_text(text: str, api_key: str) -> str:
    """Calls Gemini Flash Lite to generate a dense bullet-point summary of the text."""
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent"
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
        except (KeyError, IndexErrors):
            return "Не удалось сжать историю."

async def fold_history(messages: List[Dict[str, Any]], api_key: str, max_tokens: int = 4000) -> List[Dict[str, Any]]:
    """
    Checks if the total length of messages exceeds max_tokens.
    If so, summarizes the oldest messages and replaces them with a single summary message,
    while keeping the most recent 4 messages untouched.
    """
    # Each message is expected to have 'role' and 'content' keys.
    total_tokens = sum(count_tokens(msg["content"]) for msg in messages)
    
    if total_tokens <= max_tokens or len(messages) <= 6:
        return messages

    print(f"[Wiki-Fold] Context length is {total_tokens} tokens. Folding oldest messages...")

    # Keep the last 4 messages untouched, summarize everything before them
    foldable_msgs = messages[:-4]
    retained_msgs = messages[-4:]

    # Compile foldable text
    foldable_text_lines = []
    for msg in foldable_msgs:
        role = "Пользователь" if msg["role"] == "user" else "Ассистент"
        foldable_text_lines.append(f"{role}: {msg['content']}")
    
    foldable_text = "\n\n".join(foldable_text_lines)
    
    try:
        summary = await summarize_text(foldable_text, api_key)
        summary_msg = {
            "role": "user",
            "content": f"[Служебный системный контекст: Краткое содержание предыдущей части беседы]\n{summary}"
        }
        print(f"[Wiki-Fold] Successfully folded history. New context length: {count_tokens(summary)} tokens.")
        return [summary_msg] + retained_msgs
    except Exception as e:
        print(f"[Wiki-Fold Error] Failed to summarize old context: {e}. Retaining original history.")
        return messages
