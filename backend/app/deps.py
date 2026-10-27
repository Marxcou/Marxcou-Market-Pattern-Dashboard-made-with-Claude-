from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.security import load_session

SESSION_COOKIE = "session"
DB = Annotated[Session, Depends(get_db)]


def current_user_allow_pw_change(
    request: Request, db: DB, session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> User:
    if not session:
        raise HTTPException(401, "Nicht angemeldet")
    loaded = load_session(db, session)
    if loaded is None:
        raise HTTPException(401, "Sitzung abgelaufen")
    user, sess = loaded
    if request.method not in ("GET", "HEAD", "OPTIONS") and x_csrf_token != sess.csrf_token:
        raise HTTPException(403, "CSRF token missing or invalid")
    return user


def current_user(user: Annotated[User, Depends(current_user_allow_pw_change)]) -> User:
    """As above, but an account with a one-time password may only change its password (and log out)."""
    if user.must_change_password:
        raise HTTPException(403, "Please change the password first",
                            headers={"X-Error-Code": "password_change_required"})
    return user


def admin_user(user: Annotated[User, Depends(current_user)]) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Administrators only")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
CurrentUserAllowPwChange = Annotated[User, Depends(current_user_allow_pw_change)]
AdminUser = Annotated[User, Depends(admin_user)]
