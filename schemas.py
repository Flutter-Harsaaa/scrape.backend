from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime


class BusinessCreate(BaseModel):
    name: str
    category: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = 0


class BusinessUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    website_status: Optional[str] = None
    lead_status: Optional[str] = None
    notes: Optional[str] = None
    next_followup_date: Optional[datetime] = None


class BusinessOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: Optional[str]
    phone: Optional[str]
    phone_type: Optional[str] = None
    website: Optional[str]
    address: Optional[str]
    rating: Optional[float]
    review_count: Optional[int]
    website_status: str
    lead_status: str
    notes: Optional[str]
    next_followup_date: Optional[datetime] = None
    created_at: datetime


class PaginatedBusinessOut(BaseModel):
    items: list[BusinessOut]
    total: int
    page: int
    limit: int
    pages: int


class MessageCreate(BaseModel):
    business_id: int
    prompt_type: Optional[str] = "initial"
    platform: Optional[str] = "whatsapp"


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    business_id: int
    generated_message: str
    channel: Optional[str]
    status: Optional[str]
    provider: Optional[str]
    provider_message_id: Optional[str]
    sent_at: Optional[datetime]
    error_message: Optional[str]
    created_at: datetime


class WebsiteCheckRequest(BaseModel):
    url: str


class WebsiteCheckResult(BaseModel):
    status: str  # NO_WEBSITE, WORKING, BROKEN
    detail: Optional[str] = None


class DashboardStats(BaseModel):
    total: int
    no_website: int
    broken_website: int
    contacted: int
    interested: int
    won: int


class TimePoint(BaseModel):
    date: str
    new: int
    cumulative: int


class NameValue(BaseModel):
    name: str
    value: int


class Analytics(BaseModel):
    leads_over_time: list[TimePoint]
    lead_status: list[NameValue]
    website_status: list[NameValue]
    phone_type: list[NameValue]
    top_categories: list[NameValue]
    funnel: list[NameValue]
    messages_sent: int


class BulkIds(BaseModel):
    ids: list[int]


class BulkStatus(BaseModel):
    ids: list[int]
    status: str
