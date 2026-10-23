from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.deps import CurrentUser, DbSession
from app.errors import AppError, unauthorized
from app.models import User
from app.schemas import ErrorOut, LoginRequest, RegisterRequest, TokenOut, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/auth/register", status_code=201, response_model=UserOut, responses={409: {"model": ErrorOut}})
def register(body: RegisterRequest, db: DbSession) -> User:
    user = User(email=body.email.lower(), full_name=body.full_name.strip(), password_hash=hash_password(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "EMAIL_TAKEN", "A user with this email already exists") from None
    return user


@router.post("/auth/login", response_model=TokenOut, responses={401: {"model": ErrorOut}})
def login(body: LoginRequest, db: DbSession) -> TokenOut:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    # The same message for "no such user" and "wrong password": do not reveal which emails exist.
    if user is None or not verify_password(body.password, user.password_hash):
        raise unauthorized("Invalid email or password")
    return TokenOut(
        access_token=create_access_token(user.id),
        expires_in=get_settings().access_token_expire_minutes * 60,
    )


@router.get("/users/me", response_model=UserOut, responses={401: {"model": ErrorOut}})
def me(user: CurrentUser) -> User:
    return user
