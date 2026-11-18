"""Each contractor has one fixed row colour, used on every month, contractor and sheet page.
A new contractor gets the next unused colour automatically; a manager can change it."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Contractor

# Soft, clearly different colours; dark text stays readable on all of them (same list as migration 0005).
PALETTE = ["#CFE3FA", "#D3F0D9", "#FFE2C2", "#E6D9F7", "#FAD4DE", "#CDEFEA", "#FFF0B8", "#EBDDCB",
           "#DDEFC2", "#F9D3C9", "#C9DDF0", "#F2D6EC", "#D5E8E0", "#E4E4E4", "#D9D3F5", "#C8EAF5"]


def next_color(db: Session) -> str:
    used = [c.upper() for c in db.scalars(select(Contractor.color).where(Contractor.color.is_not(None)))]
    for c in PALETTE:
        if c.upper() not in used:
            return c
    return PALETTE[len(used) % len(PALETTE)]
