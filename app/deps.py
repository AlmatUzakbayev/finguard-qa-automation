"""Shared FastAPI dependencies."""

from typing import Annotated

import jwt
from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import unauthorized
from app.models import User
from app.security import decode_access_token

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(db: DbSession, authorization: Annotated[str | None, Header()] = None) -> User:
    """Resolve "Authorization: Bearer <token>" to a User, or fail with 401."""
    if not authorization:
        raise unauthorized("Missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise unauthorized("Authorization header must be 'Bearer <token>'")
    try:
        user_id = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise unauthorized("Token has expired") from None
    except (jwt.InvalidTokenError, ValueError):
        raise unauthorized("Invalid token") from None
    user = db.get(User, user_id)
    if user is None:
        raise unauthorized("Invalid token")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
