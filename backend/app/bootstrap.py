import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User
from app.security import hash_password

log = logging.getLogger(__name__)

# Placeholders from .env.example: an admin is never created with these.
PLACEHOLDER_EMAILS = {"admin@example.com"}
PLACEHOLDER_PASSWORDS = {"change-me-now"}


def is_placeholder(email: str, password: str) -> bool:
    return email.strip().lower() in PLACEHOLDER_EMAILS or password in PLACEHOLDER_PASSWORDS


def apply_admin_credentials(db: Session, email: str, password: str) -> str:
    """Sets the admin's email and password from the given values (creates or updates the admin).

    Returns: "created" or "updated". Used by the CLI command `python -m app.admin_cli`.
    """
    email = email.strip().lower()
    admin = db.scalar(select(User).where(User.email == email)) or db.scalar(
        select(User).where(User.role == "admin").order_by(User.id))
    if admin is None:
        db.add(User(email=email, display_name="Administrator", role="admin",
                    password_hash=hash_password(password)))
        db.commit()
        return "created"
    admin.email = email
    admin.role = "admin"
    admin.password_hash = hash_password(password)
    db.commit()
    return "updated"


def ensure_admin(db: Session) -> None:
    """Creates the first admin from ADMIN_EMAIL/ADMIN_PASSWORD at startup (only if none exists yet).

    An existing admin is never overwritten (a password changed in the app stays in place).
    If ADMIN_EMAIL differs from the existing admin, a warning with a pointer to the CLI command appears in the log.
    """
    s = get_settings()
    if not s.admin_email or not s.admin_password:
        return
    email = s.admin_email.strip().lower()
    admins = list(db.scalars(select(User).where(User.role == "admin")))
    if admins:
        if email not in {a.email for a in admins}:
            log.warning(
                "ADMIN_EMAIL from .env (%s) does not match any existing admin (%s). The .env credentials are "
                "only applied on the very first start. "
                "To apply them: docker compose run --rm api python -m app.admin_cli",
                email, ", ".join(a.email for a in admins))
        return
    if is_placeholder(email, s.admin_password):
        log.error(
            "No admin created: ADMIN_EMAIL/ADMIN_PASSWORD in .env still contain the placeholders from .env.example. "
            "Please enter your own values in .env and restart.")
        return
    db.add(User(email=email, display_name="Administrator", role="admin",
                password_hash=hash_password(s.admin_password)))
    db.commit()
