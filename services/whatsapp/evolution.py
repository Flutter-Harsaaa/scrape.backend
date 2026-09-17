import os
import httpx
from urllib.parse import quote
from dotenv import load_dotenv

load_dotenv()

EVOLUTION_API_URL = os.getenv(
    "EVOLUTION_API_URL",
    "http://localhost:8080"
)

EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "lead gen")


async def send_whatsapp_message(phone: str, text: str):
    if not EVOLUTION_API_KEY:
        raise RuntimeError("EVOLUTION_API_KEY is not configured")

    instance = quote(EVOLUTION_INSTANCE, safe="")

    url = (
        f"{EVOLUTION_API_URL.rstrip('/')}"
        f"/message/sendText/{instance}"
    )

    payload = {
        "number": phone,
        "text": text,
    }

    headers = {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            json=payload,
            headers=headers,
        )

    if response.is_error:
        raise RuntimeError(
            f"Evolution API error {response.status_code}: "
            f"{response.text}"
        )

    return response.json()