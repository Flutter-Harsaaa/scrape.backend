from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class Business(Base):
    __tablename__ = "businesses"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    category = Column(String(100))
    phone = Column(String(50))
    phone_type = Column(String(20), default="unknown")
    country_code = Column(String(2), nullable=True)
    phone_normalized = Column(String(30), nullable=True)
    website = Column(String(500))
    address = Column(Text)
    rating = Column(Float)
    review_count = Column(Integer, default=0)
    website_status = Column(
        String(20),
        default="UNCHECKED"
    )
    lead_status = Column(
        String(20),
        default="NEW"
    )
    notes = Column(Text)
    next_followup_date = Column(
        DateTime(timezone=True),
        nullable=True
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    # Existing generated/outreach messages
    messages = relationship(
        "Message",
        back_populates="business",
        cascade="all, delete-orphan"
    )

    # WhatsApp conversations for this lead
    whatsapp_conversations = relationship(
        "WhatsAppConversation",
        back_populates="business",
        cascade="all, delete-orphan"
    )


class Message(Base):
    """
    Existing lead-generation/outreach message.

    Keep this separate from WhatsAppMessage because the existing
    frontend and lead pipeline already depend on this table.
    """

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(
        Integer,
        ForeignKey("businesses.id"),
        nullable=False
    )

    generated_message = Column(Text, nullable=False)

    channel = Column(String(20), default="whatsapp")
    status = Column(String(20), default="DRAFT")
    provider = Column(String(30), nullable=True)
    provider_message_id = Column(String(255), nullable=True)

    sent_at = Column(
        DateTime(timezone=True),
        nullable=True
    )
    error_message = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    business = relationship(
        "Business",
        back_populates="messages"
    )


class WhatsAppConversation(Base):
    """
    One WhatsApp conversation with one lead.
    """

    __tablename__ = "whatsapp_conversations"

    id = Column(Integer, primary_key=True, index=True)

    business_id = Column(
        Integer,
        ForeignKey("businesses.id"),
        nullable=False,
        index=True
    )

    # Evolution/WhatsApp identifiers
    instance_name = Column(
        String(100),
        nullable=False,
        index=True
    )

    phone_number = Column(
        String(30),
        nullable=False,
        index=True
    )

    whatsapp_jid = Column(
        String(100),
        nullable=True,
        index=True
    )

    # Conversation preview
    last_message = Column(
        Text,
        nullable=True
    )

    last_message_at = Column(
        DateTime(timezone=True),
        nullable=True,
        index=True
    )

    unread_count = Column(
        Integer,
        default=0,
        nullable=False
    )

    is_archived = Column(
        Boolean,
        default=False,
        nullable=False
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    business = relationship(
        "Business",
        back_populates="whatsapp_conversations"
    )

    messages = relationship(
        "WhatsAppMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="WhatsAppMessage.message_timestamp"
    )


class WhatsAppMessage(Base):
    """
    Individual WhatsApp message received from or sent to a lead.
    """

    __tablename__ = "whatsapp_messages"

    id = Column(Integer, primary_key=True, index=True)

    conversation_id = Column(
        Integer,
        ForeignKey("whatsapp_conversations.id"),
        nullable=False,
        index=True
    )

    # Evolution/WhatsApp message ID
    provider_message_id = Column(
        String(255),
        nullable=True,
        unique=True,
        index=True
    )

    # incoming / outgoing
    direction = Column(
        String(20),
        nullable=False
    )

    # text / image / audio / video / document / etc.
    message_type = Column(
        String(30),
        default="text",
        nullable=False
    )

    content = Column(
        Text,
        nullable=True
    )

    # SENDING / SENT / DELIVERED / READ / PLAYED / FAILED / RECEIVED
    status = Column(
        String(30),
        default="RECEIVED",
        nullable=False
    )

    # WhatsApp timestamp
    message_timestamp = Column(
        DateTime(timezone=True),
        nullable=True,
        index=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    conversation = relationship(
        "WhatsAppConversation",
        back_populates="messages"
    )