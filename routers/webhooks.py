import os

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from database import get_db
import models

router = APIRouter()

EVOLUTION_WEBHOOK_SECRET = os.getenv(
    "EVOLUTION_WEBHOOK_SECRET",
    ""
)


def map_evolution_status(evolution_status: str) -> str | None:
    """
    Convert Evolution/Baileys message statuses
    into our application's message statuses.
    """

    status_map = {
        "PENDING": "SENDING",
        "SERVER_ACK": "SENT",
        "DELIVERY_ACK": "DELIVERED",
        "READ": "READ",
        "PLAYED": "PLAYED",
    }

    return status_map.get(evolution_status)


@router.post("/evolution")
async def evolution_webhook(
    request: Request,
    x_webhook_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    if not EVOLUTION_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=500,
            detail="EVOLUTION_WEBHOOK_SECRET is not configured",
        )

    if x_webhook_secret != EVOLUTION_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=401,
            detail="Invalid webhook secret",
        )

    payload = await request.json()
    print("Evolution webhook payload:")
    print(payload)

    event = payload.get("event")
    data = payload.get("data") or {}

    # We only need message status updates.
    if event != "messages.update":
        return {
            "status": "ignored",
            "event": event,
        }

    provider_message_id = data.get("keyId")
    evolution_status = data.get("status")

    if not provider_message_id:
        return {
            "status": "ignored",
            "reason": "missing keyId",
        }

    if not evolution_status:
        return {
            "status": "ignored",
            "reason": "missing status",
        }

    new_status = map_evolution_status(evolution_status)

    if not new_status:
        return {
            "status": "ignored",
            "reason": f"unsupported status: {evolution_status}",
        }

    message = (
        db.query(models.Message)
        .filter(
            models.Message.provider_message_id
            == provider_message_id
        )
        .first()
    )

    if not message:
        return {
            "status": "ignored",
            "reason": "message not found",
            "provider_message_id": provider_message_id,
        }

    message.status = new_status

    # SERVER_ACK is the point at which we consider
    # the message successfully sent.
    if evolution_status == "SERVER_ACK":
        from datetime import datetime, timezone

        message.sent_at = datetime.now(timezone.utc)
        message.error_message = None

        business = (
            db.query(models.Business)
            .filter(
                models.Business.id == message.business_id
            )
            .first()
        )

        if business:
            business.lead_status = "CONTACTED"

    db.commit()

    return {
        "status": "processed",
        "message_id": message.id,
        "provider_message_id": provider_message_id,
        "evolution_status": evolution_status,
        "application_status": new_status,
    }