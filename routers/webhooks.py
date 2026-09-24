import os
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from database import get_db
import models


router = APIRouter()

EVOLUTION_WEBHOOK_SECRET = os.getenv("EVOLUTION_WEBHOOK_SECRET", "")


def map_evolution_status(evolution_status: str) -> str | None:
    status_map = {
        "PENDING": "SENDING",
        "SERVER_ACK": "SENT",
        "DELIVERY_ACK": "DELIVERED",
        "READ": "READ",
        "PLAYED": "PLAYED",
    }

    return status_map.get(evolution_status)


def extract_message_content(message_data: dict) -> tuple[str | None, str]:
    """
    Extract text/content and message type from an Evolution messages.upsert payload.
    """

    if not isinstance(message_data, dict):
        return None, "unknown"

    # Normal text message
    if isinstance(message_data.get("conversation"), str):
        return message_data["conversation"], "conversation"

    # Extended text message
    extended = message_data.get("extendedTextMessage")

    if isinstance(extended, dict):
        text = extended.get("text")

        if isinstance(text, str):
            return text, "extendedTextMessage"

    # Image with caption
    image_message = message_data.get("imageMessage")

    if isinstance(image_message, dict):
        caption = image_message.get("caption")

        if isinstance(caption, str) and caption:
            return caption, "imageMessage"

        return "[Image]", "imageMessage"

    # Video with caption
    video_message = message_data.get("videoMessage")

    if isinstance(video_message, dict):
        caption = video_message.get("caption")

        if isinstance(caption, str) and caption:
            return caption, "videoMessage"

        return "[Video]", "videoMessage"

    # Document
    if isinstance(message_data.get("documentMessage"), dict):
        return "[Document]", "documentMessage"

    # Audio
    if isinstance(message_data.get("audioMessage"), dict):
        return "[Audio]", "audioMessage"

    # Sticker
    if isinstance(message_data.get("stickerMessage"), dict):
        return "[Sticker]", "stickerMessage"

    return None, "unknown"


def extract_phone_from_jid(jid: str | None) -> str | None:
    """
    Extract phone number from a WhatsApp JID.

    Example:
        919022642659@s.whatsapp.net
        -> 919022642659
    """

    if not jid or "@" not in jid:
        return None

    number, jid_type = jid.split("@", 1)

    if jid_type != "s.whatsapp.net":
        return None

    number = "".join(char for char in number if char.isdigit())

    return number or None


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
    instance_name = payload.get("instance")
    data = payload.get("data") or {}

    # ---------------------------------------------------------
    # messages.upsert
    # ---------------------------------------------------------

    if event == "messages.upsert":

        # Evolution normally sends a single message object here.
        # Handle a list as well for safety.
        items = data if isinstance(data, list) else [data]

        processed = []

        for item in items:

            if not isinstance(item, dict):
                continue

            key = item.get("key") or {}
            message_data = item.get("message") or {}

            provider_message_id = key.get("id")
            remote_jid = key.get("remoteJid")
            remote_jid_alt = key.get("remoteJidAlt")
            from_me = bool(key.get("fromMe"))

            if not provider_message_id:
                continue

            # Avoid storing the same WhatsApp message twice.
            existing = (
                db.query(models.WhatsAppMessage)
                .filter(
                    models.WhatsAppMessage.provider_message_id
                    == provider_message_id
                )
                .first()
            )

            if existing:
                processed.append(existing.id)
                continue

            # Prefer the normal WhatsApp JID.
            phone_number = extract_phone_from_jid(remote_jid)

            if not phone_number:
                phone_number = extract_phone_from_jid(remote_jid_alt)

            # We currently only associate normal WhatsApp phone JIDs.
            if not phone_number:
                print(
                    f"Skipping WhatsApp message because phone number "
                    f"could not be extracted: {remote_jid}"
                )
                continue

            content, message_type = extract_message_content(message_data)

            if content is None:
                content = "[Unsupported message]"

            direction = "outgoing" if from_me else "incoming"

            # Find the lead using normalized phone first.
            normalized_phone = normalize_phone(phone_number)

            business = None

            all_businesses = (
                db.query(models.Business)
                .filter(models.Business.phone.isnot(None))
                .all()
            )

            for candidate in all_businesses:
                candidate_phone = normalize_phone(candidate.phone)

                if candidate_phone == normalized_phone:
                    business = candidate
                    break

            if not business:
                print(
                    f"No lead found for WhatsApp number: {phone_number}"
                )
                continue

            # Find or create conversation.
            conversation = (
                db.query(models.WhatsAppConversation)
                .filter(
                    models.WhatsAppConversation.instance_name
                    == instance_name,
                    models.WhatsAppConversation.phone_number
                    == phone_number,
                )
                .first()
            )

            if not conversation:
                conversation = models.WhatsAppConversation(
                    business_id=business.id,
                    instance_name=instance_name,
                    phone_number=phone_number,
                    whatsapp_jid=remote_jid,
                    last_message=content,
                    last_message_at=datetime.now(timezone.utc),
                    unread_count=0,
                    is_archived=False,
                )

                db.add(conversation)
                db.flush()

            timestamp = item.get("messageTimestamp")

            message_timestamp = None

            if timestamp:
                try:
                    message_timestamp = datetime.fromtimestamp(
                        int(timestamp),
                        tz=timezone.utc,
                    )
                except (ValueError, TypeError, OverflowError):
                    message_timestamp = datetime.now(timezone.utc)

            if not message_timestamp:
                message_timestamp = datetime.now(timezone.utc)

            whatsapp_message = models.WhatsAppMessage(
                conversation_id=conversation.id,
                provider_message_id=provider_message_id,
                direction=direction,
                message_type=message_type,
                content=content,
                status=(
                    "SENT"
                    if from_me
                    else "RECEIVED"
                ),
                message_timestamp=message_timestamp,
            )

            db.add(whatsapp_message)

            conversation.last_message = content
            conversation.last_message_at = message_timestamp
            conversation.whatsapp_jid = remote_jid

            if not from_me:
                conversation.unread_count = (
                    conversation.unread_count or 0
                ) + 1

            if from_me:
                business.lead_status = "CONTACTED"

            db.flush()

            processed.append(whatsapp_message.id)

        db.commit()

        return {
            "status": "processed",
            "event": event,
            "processed_message_ids": processed,
        }

    # ---------------------------------------------------------
    # messages.update
    # ---------------------------------------------------------

    if event == "messages.update":

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

        # First look for the new WhatsApp workspace message.
        whatsapp_message = (
            db.query(models.WhatsAppMessage)
            .filter(
                models.WhatsAppMessage.provider_message_id
                == provider_message_id
            )
            .first()
        )

        if whatsapp_message:
            whatsapp_message.status = new_status
            db.commit()

            return {
                "status": "processed",
                "message_type": "whatsapp_message",
                "provider_message_id": provider_message_id,
                "evolution_status": evolution_status,
                "application_status": new_status,
            }

        # Keep compatibility with the existing lead-generation
        # Message table.
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

        if evolution_status == "SERVER_ACK":
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
            "message_type": "legacy_message",
            "message_id": message.id,
            "provider_message_id": provider_message_id,
            "evolution_status": evolution_status,
            "application_status": new_status,
        }

    # ---------------------------------------------------------
    # Other Evolution events
    # ---------------------------------------------------------

    return {
        "status": "ignored",
        "event": event,
    }

def normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None

    digits = re.sub(r"\D", "", phone)

    if not digits:
        return None

    # Indian 10-digit number
    if len(digits) == 10:
        return f"91{digits}"

    # Already in international Indian format
    if len(digits) == 12 and digits.startswith("91"):
        return digits

    return digits