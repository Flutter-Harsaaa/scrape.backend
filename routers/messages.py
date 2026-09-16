from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
import models
import schemas
import json
from services.ai_service import generate_outreach_message
from services.whatsapp.evolution import send_whatsapp_message

router = APIRouter()


@router.get("/{business_id}", response_model=list[schemas.MessageOut])
def get_messages(business_id: int, db: Session = Depends(get_db)):
    return (
        db.query(models.Message)
        .filter(models.Message.business_id == business_id)
        .order_by(models.Message.created_at.desc())
        .all()
    )


@router.post("", response_model=schemas.MessageOut, status_code=201)
async def generate_message(data: schemas.MessageCreate, db: Session = Depends(get_db)):
    business = db.query(models.Business).filter(models.Business.id == data.business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    messages = await generate_outreach_message(
        name=business.name,
        category=business.category or "business",
        rating=business.rating,
        review_count=business.review_count,
        website_status=business.website_status,
        prompt_type=data.prompt_type,
        platform=data.platform,
    )

    message = models.Message(
        business_id=business.id,
        generated_message=json.dumps(messages),
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


@router.post("/{business_id}/send", response_model=schemas.MessageOut)
async def send_message(
    business_id: int,
    db: Session = Depends(get_db),
):
    business = (
        db.query(models.Business)
        .filter(models.Business.id == business_id)
        .first()
    )

    if not business:
        raise HTTPException(
            status_code=404,
            detail="Business not found"
        )

    if not business.phone:
        raise HTTPException(
            status_code=400,
            detail="Business does not have a phone number"
        )

    message = (
        db.query(models.Message)
        .filter(models.Message.business_id == business_id)
        .order_by(models.Message.created_at.desc())
        .first()
    )

    if not message:
        raise HTTPException(
            status_code=404,
            detail="No generated message found for this business"
        )

    # Mark as being sent while Evolution processes the request.
    message.status = "SENDING"
    message.channel = "whatsapp"
    message.provider = "evolution"
    message.error_message = None

    db.commit()
    db.refresh(message)

    try:
        result = await send_whatsapp_message(
            phone=business.phone,
            text=message.generated_message,
        )

        provider_message_id = (
            result.get("key", {}).get("id")
            if isinstance(result, dict)
            else None
        )

        if not provider_message_id:
            raise RuntimeError(
                "Evolution API did not return a provider message ID"
            )

        # Do NOT mark SENT or CONTACTED here.
        # Evolution webhook will update the actual status.
        message.provider_message_id = provider_message_id

        db.commit()
        db.refresh(message)

        return message

    except Exception as exc:
        message.status = "FAILED"
        message.error_message = str(exc)

        db.commit()
        db.refresh(message)

        raise HTTPException(
            status_code=502,
            detail="WhatsApp message failed to send"
        )