"""Pydantic request and response schemas for validation."""
from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, Field, EmailStr, field_validator


class RoomTypeSchema(BaseModel):
    id: str
    name: str
    description: str
    base_occupancy: int
    max_occupancy: int
    total_inventory: int
    base_price_paise: int
    image_url: str

    class Config:
        from_attributes = True


class RatePlanSchema(BaseModel):
    id: str
    name: str
    description: str
    breakfast_addon_paise: int
    is_active: bool

    class Config:
        from_attributes = True


class NightlyPriceSchema(BaseModel):
    date: date
    base_rate_paise: int
    breakfast_addon_paise: int
    discount_paise: int
    taxable_amount_paise: int
    gst_bps: int
    gst_paise: int
    total_night_paise: int


class PriceQuoteResponse(BaseModel):
    room_type_id: str
    rate_plan_id: str
    check_in: date
    check_out: date
    num_guests: int
    nights: List[NightlyPriceSchema]
    room_total_paise: int
    discount_paise: int
    gst_paise: int
    grand_total_paise: int
    promo_code: Optional[str] = None


class HoldRequestSchema(BaseModel):
    room_type_id: str
    rate_plan_id: str
    check_in: date
    check_out: date
    num_guests: int = Field(default=1, ge=1, le=10)
    num_rooms: int = Field(default=1, ge=1, le=5)
    guest_name: str = Field(min_length=2, max_length=100)
    guest_email: EmailStr
    guest_phone: str = Field(min_length=8, max_length=20)
    dpdp_consent: bool = Field(default=False)
    promo_code: Optional[str] = None

    @field_validator("check_out")
    @classmethod
    def validate_dates(cls, v: date, info):
        check_in = info.data.get("check_in")
        if check_in and v <= check_in:
            raise ValueError("check_out must be after check_in")
        return v

    @field_validator("dpdp_consent")
    @classmethod
    def validate_consent(cls, v: bool):
        if not v:
            raise ValueError("DPDP consent is required to create a booking hold")
        return v
