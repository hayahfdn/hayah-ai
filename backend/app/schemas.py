"""API request/response models (validated input for every endpoint)."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from datetime import date as Day
from decimal import Decimal

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.models import (
    ApprovalStatus, ConstructionStatus, DeliveryStatus, MaintenanceStatus, MediaCategory,
    PaymentStatus, ReviewKind, ReviewStatus, Role, TxKind, VideoStatus,
)

EmailStr = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, max_length=255,
                                          pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]
PHONE = Field(default=None, max_length=40, pattern=r"^[+0-9 ()-]*$")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- auth / users ----------
class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(ORM):
    id: int
    email: str
    full_name: str
    role: Role
    is_active: bool
    preferred_lang: str
    phone: str | None
    contractor_id: int | None
    last_login_at: datetime | None
    ui_zoom: int | None = None
    team_stage: str | None = None


TEAM_STAGE = Field(default=None, pattern="^(intake|customer|delivery)$")


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    role: Role
    password: str = Field(min_length=10, max_length=200)
    preferred_lang: str = Field(default="ar", pattern="^(ar|en)$")
    phone: str | None = PHONE
    contractor_id: int | None = None
    team_stage: str | None = TEAM_STAGE


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    role: Role | None = None
    is_active: bool | None = None
    preferred_lang: str | None = Field(default=None, pattern="^(ar|en)$")
    phone: str | None = PHONE
    contractor_id: int | None = None
    team_stage: str | None = TEAM_STAGE
    password: str | None = Field(default=None, min_length=10, max_length=200)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=200)


# ---------- contractors ----------
class ContractorIn(BaseModel):
    code: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=200)
    country: str | None = Field(default=None, max_length=80)
    phone: str | None = PHONE
    is_active: bool = True
    notes: str | None = Field(default=None, max_length=5000)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")


class ContractorUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    country: str | None = Field(default=None, max_length=80)
    phone: str | None = PHONE
    is_active: bool | None = None
    notes: str | None = Field(default=None, max_length=5000)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")


class ContractorOut(ORM):
    id: int
    code: str
    name: str
    country: str | None
    phone: str | None
    is_active: bool
    notes: str | None
    color: str | None = None


# ---------- projects ----------
class ProjectBase(BaseModel):
    order_date: date | None = None
    customer_name: str | None = Field(default=None, max_length=200)
    customer_phone: str | None = PHONE
    customer_phone_country: str | None = Field(default=None, max_length=2, pattern="^[A-Za-z]{2}$")
    country: str | None = Field(default=None, max_length=80)
    city: str | None = Field(default=None, max_length=120)
    village: str | None = Field(default=None, max_length=120)
    well_type: str | None = Field(default=None, max_length=80)
    sales_source: str | None = Field(default=None, max_length=120)
    contractor_id: int | None = None
    sale_amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    cost: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    payment_method: str | None = Field(default=None, max_length=60)
    extras: str | None = Field(default=None, max_length=200)
    shopify_order: str | None = Field(default=None, max_length=60)
    dedication: str | None = Field(default=None, max_length=2000)
    received_date: date | None = None
    currency: str = Field(default="USD", pattern="^[A-Z]{3}$")
    payment_status: PaymentStatus = PaymentStatus.unpaid
    construction_status: ConstructionStatus = ConstructionStatus.new_order
    construction_start_date: date | None = None
    completion_date: date | None = None
    final_video_link: str | None = Field(default=None, max_length=500)
    video_status: VideoStatus = VideoStatus.none
    next_maintenance_date: date | None = None
    notes: str | None = Field(default=None, max_length=10000)

    @field_validator("final_video_link")
    @classmethod
    def _https(cls, v):
        if v and not v.startswith("https://"):
            raise ValueError("Link must start with https://")
        return v

    @field_validator("well_type")
    @classmethod
    def _one_of_four(cls, v):
        from app.services.well_types import ALL, TYPES, normalize
        v = normalize(v)
        if v is not None and v not in ALL:
            raise ValueError("Well type must be one of: " + "، ".join(TYPES))
        return v


class ProjectCreate(ProjectBase):
    well_id: int = Field(gt=0, lt=10**12)


class ProjectUpdate(BaseModel):
    """Delivery status/date are deliberately absent: they only change through an
    approved delivery confirmation."""
    expected_version: int | None = Field(default=None, description="Optimistic lock: reject if the project changed")
    order_date: date | None = None
    customer_name: str | None = Field(default=None, max_length=200)
    customer_phone: str | None = PHONE
    customer_phone_country: str | None = Field(default=None, max_length=2, pattern="^[A-Za-z]{2}$")
    country: str | None = Field(default=None, max_length=80)
    city: str | None = Field(default=None, max_length=120)
    village: str | None = Field(default=None, max_length=120)
    well_type: str | None = Field(default=None, max_length=80)
    sales_source: str | None = Field(default=None, max_length=120)
    contractor_id: int | None = None
    sale_amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    cost: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    payment_method: str | None = Field(default=None, max_length=60)
    extras: str | None = Field(default=None, max_length=200)
    shopify_order: str | None = Field(default=None, max_length=60)
    dedication: str | None = Field(default=None, max_length=2000)
    received_date: date | None = None
    currency: str | None = Field(default=None, pattern="^[A-Z]{3}$")
    payment_status: PaymentStatus | None = None
    construction_status: ConstructionStatus | None = None
    construction_start_date: date | None = None
    completion_date: date | None = None
    final_video_link: str | None = Field(default=None, max_length=500)
    video_status: VideoStatus | None = None
    next_maintenance_date: date | None = None
    notes: str | None = Field(default=None, max_length=10000)
    model_config = ConfigDict(extra="forbid")
    _https = field_validator("final_video_link")(ProjectBase._https.__func__)
    _types = field_validator("well_type")(ProjectBase._one_of_four.__func__)


class ProjectOut(ORM):
    id: int
    well_id: int
    order_date: date | None
    customer_name: str | None
    customer_phone: str | None
    customer_phone_e164: str | None = None
    customer_phone_country: str | None = None
    customer_phone_status: str | None = None
    country: str | None
    city: str | None
    village: str | None
    well_type: str | None
    sales_source: str | None
    source_group: str | None = None
    contractor_id: int | None
    contractor: ContractorOut | None
    sale_amount: Decimal | None
    cost: Decimal | None
    payment_method: str | None
    extras: str | None
    shopify_order: str | None
    dedication: str | None = None
    received_date: date | None
    currency: str
    payment_status: PaymentStatus
    construction_status: ConstructionStatus
    construction_start_date: date | None
    completion_date: date | None
    delivery_status: DeliveryStatus
    delivery_date: date | None
    delivery_estimated: bool = False
    raw_media_folder_id: str | None
    raw_media_folder_url: str | None
    final_video_link: str | None
    video_status: VideoStatus
    maintenance_status: MaintenanceStatus
    last_maintenance_date: date | None
    next_maintenance_date: date | None
    notes: str | None
    merged_into_id: int | None
    is_sample: bool
    plaque_status: str | None = None
    plaque_media_id: int | None = None
    plaque_approved_at: datetime | None = None
    plaque_approved_by: str | None = None
    version: int
    created_at: datetime
    updated_at: datetime
    listed_at: datetime | None = None
    addon_sacrifices: list["AddonSacrificeOut"] = []


class AddonSacrificeOut(ORM):
    """A sacrifice created from this well's add-on (selling price only; never the cost)."""
    sacrifice_no: int
    animal_type: str | None = None
    sale_price: Decimal | None = None
    currency: str = "USD"


class ProjectPage(BaseModel):
    items: list[ProjectOut]
    total: int
    page: int
    page_size: int


class EventOut(ORM):
    id: uuid.UUID
    project_id: int
    event_type: str
    source: str
    source_ref: str | None
    summary: str | None
    payload: dict
    actor_label: str | None
    created_at: datetime


class MergeRequestIn(BaseModel):
    source_well_id: int
    target_well_id: int
    reason: str = Field(min_length=3, max_length=2000)


# ---------- delivery ----------
class DeliveryCreate(BaseModel):
    well_id: int
    delivery_date: date
    notes: str | None = Field(default=None, max_length=5000)
    evidence_media_ids: list[int] = []


class DeliveryDecision(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=2000)


class DeliveryOut(ORM):
    id: int
    project_id: int
    status: ApprovalStatus
    delivery_date: date | None
    sender_name: str | None
    sender_phone: str | None
    source: str
    inbound_message_id: int | None
    evidence_media_ids: list
    notes: str | None
    decided_at: datetime | None
    decision_note: str | None
    created_at: datetime
    well_id: int | None = None


# ---------- maintenance ----------
class MaintenanceCreate(BaseModel):
    well_id: int
    date: date
    country: str | None = Field(default=None, max_length=80)
    location: str | None = Field(default=None, max_length=200)
    problem_type: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=10000)
    contractor_id: int | None = None
    technician: str | None = Field(default=None, max_length=200)
    repair_action: str | None = Field(default=None, max_length=10000)
    repair_cost: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="USD", pattern="^[A-Z]{3}$")
    status: MaintenanceStatus = MaintenanceStatus.open
    next_maintenance_date: date | None = None


class MaintenanceUpdate(BaseModel):
    status: MaintenanceStatus | None = None
    repair_action: str | None = Field(default=None, max_length=10000)
    repair_cost: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    technician: str | None = Field(default=None, max_length=200)
    next_maintenance_date: date | None = None
    description: str | None = Field(default=None, max_length=10000)
    model_config = ConfigDict(extra="forbid")


class MaintenanceOut(ORM):
    id: int
    maintenance_code: str
    project_id: int
    date: date
    country: str | None
    location: str | None
    problem_type: str
    description: str | None
    contractor_id: int | None
    technician: str | None
    repair_action: str | None
    repair_cost: Decimal | None
    currency: str
    status: MaintenanceStatus
    next_maintenance_date: date | None
    source: str
    created_at: datetime
    updated_at: datetime
    well_id: int | None = None


# ---------- media ----------
class MediaOut(ORM):
    id: int
    project_id: int | None
    maintenance_id: int | None
    category: MediaCategory
    filename: str
    original_filename: str | None
    mime_type: str
    size_bytes: int
    sha256: str
    drive_file_id: str | None
    drive_folder_id: str | None
    drive_url: str | None
    source: str
    sender: str | None
    captured_at: datetime | None
    processing_status: str
    created_at: datetime
    well_id: int | None = None


# ---------- review ----------
class ReviewOut(ORM):
    id: int
    kind: ReviewKind
    status: ReviewStatus
    reason: str
    inbound_message_id: int | None
    project_id: int | None
    media_asset_id: int | None
    proposed: dict
    created_at: datetime
    resolved_at: datetime | None
    resolution_note: str | None
    message_text: str | None = None
    message_sender: str | None = None
    message_group: str | None = None


class ReviewDecision(BaseModel):
    approve: bool
    well_id: int | None = Field(default=None, description="Well ID chosen by the reviewer")
    event_type: str | None = Field(default=None, max_length=60)
    note: str | None = Field(default=None, max_length=2000)


# ---------- sync / settings ----------
class SyncConflictOut(ORM):
    id: int
    tab: str
    row_key: str
    field: str
    kind: str
    db_value: str | None
    sheet_value: str | None
    status: str
    detected_at: datetime


class ConflictResolve(BaseModel):
    keep: str = Field(pattern="^(db|sheet)$")


class AISettingsIn(BaseModel):
    ai_enabled: bool
    monthly_budget_usd: float = Field(ge=0, le=20)  # hard cap: $20 a month
    min_confidence: float = Field(ge=0.5, le=1.0)
    manual_approval_over_usd: float = Field(default=0.25, ge=0, le=1000)


class ManualMessageIn(BaseModel):
    """Paste a WhatsApp message by hand (fallback when the API is not set up)."""
    text: str = Field(min_length=1, max_length=10000)
    group_label: str | None = Field(default=None, pattern="^[ABCD]$")
    sender_name: str | None = Field(default=None, max_length=200)
    sender_phone: str | None = PHONE


# ---------- finance workbook ----------
MONEY = dict(ge=0, max_digits=12, decimal_places=2)


class SacrificeFields(BaseModel):
    order_date: date | None = None
    donor_name: str | None = Field(default=None, max_length=200)
    customer_phone: str | None = PHONE
    customer_phone_country: str | None = Field(default=None, max_length=2, pattern="^[A-Za-z]{2}$")
    received_date: date | None = None
    delivery_date: date | None = None
    contractor_id: int | None = None
    animal_type: str | None = Field(default=None, max_length=60)
    cost: Decimal | None = Field(default=None, **MONEY)
    sale_price: Decimal | None = Field(default=None, **MONEY)
    currency: str | None = Field(default=None, pattern="^[A-Z]{3}$")
    payment_method: str | None = Field(default=None, max_length=60)
    extras: str | None = Field(default=None, max_length=200)
    sales_source: str | None = Field(default=None, max_length=120)
    shopify_order: str | None = Field(default=None, max_length=60)
    intention: str | None = Field(default=None, max_length=120)
    dedication: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=10000)
    model_config = ConfigDict(extra="forbid")


class SacrificeCreate(SacrificeFields):
    sacrifice_no: int | None = Field(default=None, gt=0, lt=10**11)  # empty: the next number automatically


class SacrificeBulkCreate(SacrificeFields):
    """Several sacrifices of one order at once: each gets its own next number."""
    quantity: int = Field(default=1, ge=1, le=50)


class NumberChange(BaseModel):
    new_number: int = Field(gt=0, lt=10**11)
    model_config = ConfigDict(extra="forbid")


class RenumberPlan(BaseModel):
    renames: list[dict] = []   # [{"from": 3098, "to": 3091}]
    orders: list[dict] = []    # [{"order": "1225", "numbers": [3091, 3092]}]
    token: str | None = None
    model_config = ConfigDict(extra="forbid")


class SacrificeUpdate(SacrificeFields):
    expected_version: int | None = None


class SacrificeOut(ORM):
    id: int
    sacrifice_no: int
    order_date: date | None
    donor_name: str | None
    customer_phone: str | None = None
    customer_phone_e164: str | None = None
    customer_phone_country: str | None = None
    customer_phone_status: str | None = None
    received_date: date | None
    delivery_date: date | None
    delivery_status: DeliveryStatus = DeliveryStatus.not_ready
    delivery_estimated: bool = False
    contractor_id: int | None
    animal_type: str | None
    cost: Decimal | None
    sale_price: Decimal | None
    currency: str
    payment_method: str | None
    extras: str | None
    sales_source: str | None
    source_group: str | None = None
    shopify_order: str | None
    intention: str | None
    dedication: str | None = None
    notes: str | None
    is_sample: bool
    version: int
    updated_at: datetime
    parent_project_id: int | None = None
    parent_well_id: int | None = None


class AccountOut(ORM):
    id: int
    code: str
    name: str
    kind: str
    currency: str
    notes: str | None
    is_active: bool


class AccountIn(BaseModel):
    code: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=200)
    kind: str = Field(pattern="^(bank|partner)$")
    currency: str = Field(default="USD", pattern="^[A-Z]{3}$")
    notes: str | None = Field(default=None, max_length=2000)


class TransactionFields(BaseModel):
    date: Day | None = None
    kind: TxKind | None = None
    direction: str | None = Field(default=None, pattern="^(in|out)$")
    account_id: int | None = None
    contractor_id: int | None = None
    channel: str | None = Field(default=None, max_length=80)
    category: str | None = Field(default=None, max_length=80)
    amount: Decimal | None = Field(default=None, **MONEY)
    currency: str | None = Field(default=None, pattern="^[A-Z]{3}$")
    description: str | None = Field(default=None, max_length=5000)
    reference: str | None = Field(default=None, max_length=120)
    model_config = ConfigDict(extra="forbid")


class TransactionCreate(TransactionFields):
    date: Day
    kind: TxKind
    amount: Decimal = Field(**MONEY)
    currency: str = Field(default="USD", pattern="^[A-Z]{3}$")


class TransactionUpdate(TransactionFields):
    expected_version: int | None = None


class TransactionVoid(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class TransactionOut(ORM):
    id: int
    date: Day
    kind: TxKind
    direction: str
    account_id: int | None
    contractor_id: int | None
    channel: str | None
    category: str | None
    amount: Decimal
    currency: str
    description: str | None
    reference: str | None
    voided: bool
    void_reason: str | None
    is_sample: bool
    version: int
    updated_at: datetime


class DirectDeliveryIn(BaseModel):
    """A manager records a delivery they have confirmed themselves (explicit, authorized, audited)."""
    delivery_date: date
    note: str | None = Field(default=None, max_length=2000)


TokenOut.model_rebuild()
ProjectOut.model_rebuild()
