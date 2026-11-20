from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import ADMINS, client_ip, get_current_user, require_roles
from app.models import User, utcnow
from app.schemas import LoginIn, PasswordChange, TokenOut, UserCreate, UserOut, UserUpdate
from app.security import (
    create_access_token, hash_password, login_limiter, validate_password_strength, verify_password,
)
from app.services.audit import audit, snapshot

router = APIRouter(prefix="/api/auth", tags=["auth"])
users = APIRouter(prefix="/api/users", tags=["users"])
_DUMMY_HASH = hash_password("timing-equaliser-Aa1")


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request) or "?"
    limit = get_settings().login_rate_limit_per_minute
    if not login_limiter.allow(f"ip:{ip}", limit) or not login_limiter.allow(f"user:{body.email.lower()}", limit):
        raise HTTPException(429, "Too many login attempts. Wait a minute and try again.")
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if not user or not ok or not user.is_active:
        audit(db, "auth.login_failed", "user", user.id if user else None, actor_label=body.email, ip=ip)
        db.commit()
        raise HTTPException(401, "Wrong email or password")
    user.last_login_at = utcnow()
    audit(db, "auth.login", "user", user.id, actor=user, ip=ip)
    db.commit()
    return TokenOut(access_token=create_access_token(user.id, user.role.value, user.token_version),
                    user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


ZOOM_LEVELS = (80, 90, 100, 110, 125, 150)


class PreferencesIn(BaseModel):
    ui_zoom: int | None = None


@router.patch("/me/preferences", response_model=UserOut)
def set_preferences(body: PreferencesIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Each person's own interface zoom (80, 90, 100, 110, 125 or 150 %). Stored on the user so it follows them."""
    if body.ui_zoom is not None and body.ui_zoom not in ZOOM_LEVELS:
        raise HTTPException(422, "Zoom must be one of " + ", ".join(map(str, ZOOM_LEVELS)))
    user.ui_zoom = None if body.ui_zoom in (None, 100) else body.ui_zoom
    db.commit()
    db.refresh(user)
    return user


@router.post("/logout-all", status_code=204)
def logout_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.token_version += 1
    audit(db, "auth.logout_all", "user", user.id, actor=user)
    db.commit()


@router.post("/change-password", status_code=204)
def change_password(body: PasswordChange, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is wrong")
    try:
        validate_password_strength(body.new_password)
    except ValueError as e:
        raise HTTPException(422, str(e))
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1
    audit(db, "auth.password_changed", "user", user.id, actor=user)
    db.commit()


@users.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_roles(ADMINS))):
    return list(db.scalars(select(User).order_by(User.id)))


@users.post("", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, request: Request, db: Session = Depends(get_db),
                admin: User = Depends(require_roles(ADMINS))):
    try:
        validate_password_strength(body.password)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if db.scalar(select(User).where(func.lower(User.email) == body.email.lower())):
        raise HTTPException(409, "A user with this email already exists")
    u = User(**body.model_dump(exclude={"password", "email"}), email=body.email.lower(), password_hash=hash_password(body.password))
    db.add(u)
    db.flush()
    audit(db, "user.create", "user", u.id, actor=admin, after=snapshot(u), ip=client_ip(request))
    db.commit()
    return u


@users.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, request: Request, db: Session = Depends(get_db),
                admin: User = Depends(require_roles(ADMINS))):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    before = snapshot(u)
    data = body.model_dump(exclude_unset=True)
    if "password" in data:
        try:
            validate_password_strength(data["password"])
        except ValueError as e:
            raise HTTPException(422, str(e))
        u.password_hash = hash_password(data.pop("password"))
        u.token_version += 1
    if u.id == admin.id and (data.get("role") not in (None, admin.role) or data.get("is_active") is False):
        raise HTTPException(422, "You cannot remove your own admin access")
    for k, v in data.items():
        setattr(u, k, v)
    if "role" in data or data.get("is_active") is False:
        u.token_version += 1  # force re-login with new permissions
    audit(db, "user.update", "user", u.id, actor=admin, before=before, after=snapshot(u), ip=client_ip(request))
    db.commit()
    return u
