import json
import re

import requests
from django.conf import settings
from requests import ConnectTimeout, ConnectionError, Timeout


class GeminiAPIError(Exception):
    pass


def generate_json(prompt, *, google_search=False):
    if not settings.GEMINI_API_KEY:
        raise GeminiAPIError("The Gemini API key is not configured.")

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.GEMINI_MODEL}:generateContent"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    if google_search:
        payload["tools"] = [{"google_search": {}}]

    try:
        response = requests.post(
            url,
            params={"key": settings.GEMINI_API_KEY},
            json=payload,
            timeout=30,
        )
    except (ConnectTimeout, Timeout) as exc:
        raise GeminiAPIError("The Gemini API request timed out. Check your internet connection and retry.") from exc
    except ConnectionError as exc:
        raise GeminiAPIError("Could not connect to the Gemini API. Check your internet connection and retry.") from exc
    except requests.RequestException as exc:
        raise GeminiAPIError("The Gemini API request could not be completed.") from exc

    if not response.ok:
        try:
            response_data = response.json()
        except ValueError:
            response_data = {}
        error_data = response_data.get("error") if isinstance(response_data, dict) else None
        message = error_data.get("message") if isinstance(error_data, dict) else None
        detail = f": {message}" if message else ""
        raise GeminiAPIError(f"Gemini API returned HTTP {response.status_code}{detail}")

    try:
        data = response.json()
    except ValueError as exc:
        raise GeminiAPIError("The Gemini API returned invalid JSON.") from exc

    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        error_data = data.get("error") if isinstance(data, dict) else None
        error = error_data.get("message") if isinstance(error_data, dict) else None
        raise GeminiAPIError(error or "The Gemini API returned no generated content.") from exc

    text = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text, flags=re.IGNORECASE)
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GeminiAPIError("The Gemini API response was not valid JSON.") from exc
    if not isinstance(result, list):
        raise GeminiAPIError("The Gemini API response did not contain a JSON array.")
    return result
