import os
from urllib.parse import quote

import httpx
from fastapi import APIRouter

router = APIRouter()


@router.get("/test/evolution")
async def test_evolution():
    evolution_url = os.getenv("EVOLUTION_API_URL")
    evolution_api_key = os.getenv("EVOLUTION_API_KEY")
    instance = os.getenv("EVOLUTION_INSTANCE")

    if not evolution_url or not evolution_api_key or not instance:
        return {
            "status": "error",
            "message": "Evolution API environment variables are missing"
        }

    encoded_instance = quote(instance, safe="")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{evolution_url}/instance/connectionState/{encoded_instance}",
                headers={
                    "apikey": evolution_api_key
                }
            )

        return {
            "status": "success" if response.is_success else "error",
            "evolution_status_code": response.status_code,
            "evolution_response": response.json()
        }

    except httpx.RequestError as e:
        return {
            "status": "error",
            "message": f"Could not connect to Evolution API: {str(e)}"
        }