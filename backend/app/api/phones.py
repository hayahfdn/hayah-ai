"""Phone number check used by the order forms (live preview of the E.164 number)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.deps import PROJECT_CREATORS, require_roles
from app.models import User
from app.services import phones

router = APIRouter(prefix="/api/phones", tags=["phones"])


class PhoneIn(BaseModel):
    phone: str | None = Field(default=None, max_length=40)
    country: str | None = Field(default=None, max_length=80)


@router.post("/check")
def check(body: PhoneIn, _: User = Depends(require_roles(PROJECT_CREATORS))):
    return phones.normalize(body.phone, body.country)


@router.get("/countries")
def countries(_: User = Depends(require_roles(PROJECT_CREATORS))):
    return phones.countries()
