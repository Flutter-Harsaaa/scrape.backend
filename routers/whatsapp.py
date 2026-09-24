import os
from urllib.parse import quote
from datetime import datetime, timezone

import httpx

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
import models
from services.whatsapp.evolution import send_whatsapp_message


router = APIRouter()


EVOLUTION_API_URL = os.getenv(
    "EVOLUTION_API_URL",
    "http://localhost:8080",
)

EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY")

EVOLUTION_INSTANCE = os.getenv(
    "EVOLUTION_INSTANCE",
    "lead gen",
)


def normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None

    digits = "".join(char for char in phone if char.isdigit())

    if not digits:
        return None

    # Indian 10-digit number -> 91 + number
    if len(digits) == 10:
        digits = "91" + digits

    return digits


def serialize_message(message: models.WhatsAppMessage):
    return {
        "id": message.id,
        "provider_message_id": message.provider_message_id,
        "direction": message.direction,
        "message_type": message.message_type,
        "content": message.content,
        "status": message.status,
        "message_timestamp": message.message_timestamp,
        "created_at": message.created_at,
    }


def serialize_conversation(
    conversation: models.WhatsAppConversation,
):
    business = conversation.business

    return {
        "id": conversation.id,
        "business_id": conversation.business_id,
        "business_name": business.name if business else None,
        "phone_number": conversation.phone_number,
        "last_message": conversation.last_message,
        "last_message_at": conversation.last_message_at,
        "unread_count": conversation.unread_count,
        "is_archived": conversation.is_archived,
        "lead_status": business.lead_status if business else None,
    }


@router.get("/status")
async def whatsapp_status():
    if not EVOLUTION_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="EVOLUTION_API_KEY is not configured",
        )

    if not EVOLUTION_INSTANCE:
        raise HTTPException(
            status_code=500,
            detail="EVOLUTION_INSTANCE is not configured",
        )

    instance = quote(EVOLUTION_INSTANCE, safe="")

    url = (
        f"{EVOLUTION_API_URL.rstrip('/')}"
        f"/instance/connectionState/{instance}"
    )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                url,
                headers={"apikey": EVOLUTION_API_KEY},
            )

        if response.is_error:
            raise HTTPException(
                status_code=502,
                detail="Evolution API returned an error",
            )

        data = response.json()

        return {
            "instance_name": EVOLUTION_INSTANCE,
            "state": data.get(
                "instance",
                {},
            ).get(
                "state",
                "unknown",
            ),
            "evolution_response": data,
        }

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not connect to Evolution API: {exc}",
        )


@router.get("/conversations")
def get_conversations(
    db: Session = Depends(get_db),
):
    conversations = (
        db.query(models.WhatsAppConversation)
        .order_by(
            models.WhatsAppConversation.last_message_at.desc()
        )
        .all()
    )

    return [
        serialize_conversation(conversation)
        for conversation in conversations
    ]


@router.get("/conversations/{conversation_id}/messages")
def get_conversation_messages(
    conversation_id: int,
    db: Session = Depends(get_db),
):
    conversation = (
        db.query(models.WhatsAppConversation)
        .filter(
            models.WhatsAppConversation.id == conversation_id
        )
        .first()
    )

    if not conversation:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    messages = (
        db.query(models.WhatsAppMessage)
        .filter(
            models.WhatsAppMessage.conversation_id
            == conversation_id
        )
        .order_by(
            models.WhatsAppMessage.message_timestamp.asc(),
            models.WhatsAppMessage.id.asc(),
        )
        .all()
    )

    # Opening a conversation marks incoming messages as read.
    conversation.unread_count = 0
    db.commit()

    return [
        serialize_message(message)
        for message in messages
    ]


@router.post("/conversations/{conversation_id}/messages")
async def send_conversation_message(
    conversation_id: int,
    payload: dict,
    db: Session = Depends(get_db),
):
    """
    Send a follow-up message from the WhatsApp inbox.

    This endpoint ONLY works with an already-existing conversation.
    """

    conversation = (
        db.query(models.WhatsAppConversation)
        .filter(
            models.WhatsAppConversation.id == conversation_id
        )
        .first()
    )

    if not conversation:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    text = payload.get("text")

    if not isinstance(text, str) or not text.strip():
        raise HTTPException(
            status_code=400,
            detail="Message text is required",
        )

    text = text.strip()

    try:
        result = await send_whatsapp_message(
            phone=conversation.phone_number,
            text=text,
        )

        provider_message_id = None

        if isinstance(result, dict):
            provider_message_id = (
                result.get("key", {}).get("id")
            )

        if not provider_message_id:
            raise RuntimeError(
                "Evolution API did not return a provider message ID"
            )

        message = (
            db.query(models.WhatsAppMessage)
            .filter(
                models.WhatsAppMessage.provider_message_id
                == provider_message_id
            )
            .first()
        )

        now = datetime.now(timezone.utc)

        if message:
            message.content = text
            message.direction = "outgoing"
            message.status = "SENT"

        else:
            message = models.WhatsAppMessage(
                conversation_id=conversation.id,
                provider_message_id=provider_message_id,
                direction="outgoing",
                message_type="conversation",
                content=text,
                status="SENT",
                message_timestamp=now,
            )

            db.add(message)

        conversation.last_message = text
        conversation.last_message_at = now
        conversation.unread_count = 0

        if conversation.business:
            conversation.business.lead_status = "CONTACTED"

        db.commit()
        db.refresh(message)

        return serialize_message(message)

    except Exception as exc:
        db.rollback()

        raise HTTPException(
            status_code=502,
            detail=f"WhatsApp message failed to send: {exc}",
        )


# ============================================================
# FIRST WHATSAPP OUTREACH
# ============================================================

@router.post("/leads/{business_id}/messages")
async def send_first_lead_message(
    business_id: int,
    payload: dict,
    db: Session = Depends(get_db),
):
    """
    Send the first WhatsApp outreach message for a lead.

    This endpoint is used by:
      - Leads page
      - Lead Details page

    A conversation is created ONLY when the message is
    actually being sent.
    """

    business = (
        db.query(models.Business)
        .filter(
            models.Business.id == business_id
        )
        .first()
    )

    if not business:
        raise HTTPException(
            status_code=404,
            detail="Lead not found",
        )

    # --------------------------------------------------------
    # Validate message
    # --------------------------------------------------------

    text = payload.get("text")

    if not isinstance(text, str) or not text.strip():
        raise HTTPException(
            status_code=400,
            detail="Message text is required",
        )

    text = text.strip()

    # --------------------------------------------------------
    # Validate phone
    # --------------------------------------------------------

    if not business.phone:
        raise HTTPException(
            status_code=400,
            detail="This lead does not have a phone number",
        )

    if business.phone_type == "landline":
        raise HTTPException(
            status_code=400,
            detail="Landline numbers cannot receive WhatsApp messages",
        )

    phone = normalize_phone(business.phone)

    if not phone:
        raise HTTPException(
            status_code=400,
            detail="Invalid phone number",
        )

    # --------------------------------------------------------
    # Check whether conversation already exists
    # --------------------------------------------------------

    conversation = (
        db.query(models.WhatsAppConversation)
        .filter(
            models.WhatsAppConversation.business_id
            == business.id,
            models.WhatsAppConversation.instance_name
            == EVOLUTION_INSTANCE,
            models.WhatsAppConversation.phone_number
            == phone,
        )
        .first()
    )

    try:
        # ----------------------------------------------------
        # Send message through Evolution API
        # ----------------------------------------------------

        result = await send_whatsapp_message(
            phone=phone,
            text=text,
        )

        # ----------------------------------------------------
        # Extract Evolution provider message ID
        # ----------------------------------------------------

        provider_message_id = None

        if isinstance(result, dict):
            provider_message_id = (
                result.get("key", {}).get("id")
            )

        if not provider_message_id:
            raise RuntimeError(
                "Evolution API did not return a provider message ID"
            )

        now = datetime.now(timezone.utc)

        # ----------------------------------------------------
        # Create conversation only now
        # ----------------------------------------------------

        if not conversation:
            conversation = models.WhatsAppConversation(
                business_id=business.id,
                instance_name=EVOLUTION_INSTANCE,
                phone_number=phone,
                whatsapp_jid=None,
                last_message=text,
                last_message_at=now,
                unread_count=0,
                is_archived=False,
            )

            db.add(conversation)
            db.flush()

        else:
            conversation.last_message = text
            conversation.last_message_at = now
            conversation.unread_count = 0

        # ----------------------------------------------------
        # Check webhook race condition
        # ----------------------------------------------------

        message = (
            db.query(models.WhatsAppMessage)
            .filter(
                models.WhatsAppMessage.provider_message_id
                == provider_message_id
            )
            .first()
        )

        if message:
            message.content = text
            message.direction = "outgoing"
            message.status = "SENT"

        else:
            message = models.WhatsAppMessage(
                conversation_id=conversation.id,
                provider_message_id=provider_message_id,
                direction="outgoing",
                message_type="conversation",
                content=text,
                status="SENT",
                message_timestamp=now,
            )

            db.add(message)

        # ----------------------------------------------------
        # Update lead status
        # ----------------------------------------------------

        business.lead_status = "CONTACTED"

        db.commit()

        db.refresh(conversation)
        db.refresh(message)
        db.refresh(business)

        return {
            "conversation": serialize_conversation(
                conversation
            ),
            "message": serialize_message(message),
        }

    except Exception as exc:
        db.rollback()

        raise HTTPException(
            status_code=502,
            detail=f"WhatsApp first message failed to send: {exc}",
        )


@router.get("/connection")
async def get_whatsapp_connection():
    if not EVOLUTION_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="EVOLUTION_API_KEY is not configured",
        )

    instance = quote(EVOLUTION_INSTANCE, safe="")

    url = (
        f"{EVOLUTION_API_URL.rstrip('/')}"
        f"/instance/connect/{instance}"
    )

    headers = {
        "apikey": EVOLUTION_API_KEY,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                headers=headers,
            )

        if response.is_error:
            raise HTTPException(
                status_code=response.status_code,
                detail=response.text,
            )

        return response.json()

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Evolution API connection error: {exc}",
        )


@router.delete("/connection")
async def disconnect_whatsapp():
    if not EVOLUTION_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="EVOLUTION_API_KEY is not configured",
        )

    instance = quote(EVOLUTION_INSTANCE, safe="")

    url = (
        f"{EVOLUTION_API_URL.rstrip('/')}"
        f"/instance/logout/{instance}"
    )

    headers = {
        "apikey": EVOLUTION_API_KEY,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                url,
                headers=headers,
            )

        if response.is_error:
            raise HTTPException(
                status_code=response.status_code,
                detail=response.text,
            )

        return response.json()

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Evolution API connection error: {exc}",
        )