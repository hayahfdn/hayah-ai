"""Validated JSON contract for every AI (or rules) extraction.

Whatever produces an extraction (the free rules engine today, Claude later),
its output must parse into `Extraction`. Nothing is written to the database
from an extraction directly: app.services.intake decides, and anything
uncertain becomes a Pending Review case.
"""
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

EventType = Literal["new_order", "construction_update", "delivery_confirmation", "final_video",
                    "maintenance_report", "general_note", "unknown"]


class ConstructionFields(BaseModel):
    construction_status: Literal["scheduled", "in_progress", "completed", "on_hold"] | None = None
    contractor: str | None = None
    progress_note: str | None = None


class DeliveryFields(BaseModel):
    delivery_date: date | None = None
    received_by: str | None = None
    handover_note: str | None = None


class FinalVideoFields(BaseModel):
    video_url: str | None = Field(default=None, pattern=r"^https://")


class MaintenanceFields(BaseModel):
    problem_type: str | None = None
    description: str | None = None
    technician: str | None = None
    repair_action: str | None = None
    repair_cost: float | None = Field(default=None, ge=0)


class NewOrderFields(BaseModel):
    customer_name: str | None = None
    country: str | None = None
    city: str | None = None
    village: str | None = None
    well_type: str | None = None
    sale_amount: float | None = Field(default=None, ge=0)


class Extraction(BaseModel):
    well_ids: list[int] = Field(default_factory=list, description="Every Well ID explicitly written in the message")
    well_id: int | None = Field(default=None, description="Set only when exactly one Well ID is explicit")
    event_type: EventType = "unknown"
    language: Literal["ar", "en", "mixed", "unknown"] = "unknown"
    construction: ConstructionFields | None = None
    delivery: DeliveryFields | None = None
    final_video: FinalVideoFields | None = None
    maintenance: MaintenanceFields | None = None
    new_order: NewOrderFields | None = None
    confidence: float = Field(ge=0, le=1)
    missing_fields: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    requires_human_review: bool = True
    engine: str = "rules"
    reasoning: str | None = None


def export_json_schemas() -> dict:
    return {"Extraction": Extraction.model_json_schema()}
