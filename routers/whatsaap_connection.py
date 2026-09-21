import os
import requests
from fastapi import APIRouter, HTTPException

router = APIRouter()

@router.get("/test/evolution")
def test_evolution():
    evolution_url = os.getenv("EVOLUTION_API_URL")
    api_key = os.getenv("EVOLUTION_API_KEY")
    instance = os.getenv("EVOLUTION_INSTANCE")

    if not evolution_url or not api_key or not instance:
        raise HTTPException(
            status_code=500,
            detail="Evolution API environment variables are missing"
        )

    try:
        response = requests.get(
            f"{evolution_url}/instance/connectionState/{instance}",
            headers={
                "apikey": api_key
            },
            timeout=15
        )

        return {
            "status_code": response.status_code,
            "evolution_response": response.json()
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Evolution API connection failed: {str(e)}"
        )