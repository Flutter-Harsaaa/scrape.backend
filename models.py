from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class Business(Base):
    __tablename__ = "businesses"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    category = Column(String(100))
    phone = Column(String(50))
    phone_type = Column(String(20), default="unknown")  # mobile, landline, unknown
    country_code = Column(String(2), nullable=True)
    phone_normalized = Column(String(30), nullable=True)
    website = Column(String(500))
    address = Column(Text)
    rating = Column(Float)
    review_count = Column(Integer, default=0)
    website_status = Column(String(20), default="UNCHECKED")  # UNCHECKED, NO_WEBSITE, WORKING, BROKEN
    lead_status = Column(String(20), default="NEW")  # NEW, CONTACTED, INTERESTED, WON, LOST
    notes = Column(Text)
    next_followup_date = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    messages = relationship("Message", back_populates="business", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)

    generated_message = Column(Text, nullable=False)

    channel = Column(String(20), default="whatsapp")
    status = Column(String(20), default="DRAFT")
    provider = Column(String(30), nullable=True)
    provider_message_id = Column(String(255), nullable=True)

    sent_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    business = relationship("Business", back_populates="messages")
