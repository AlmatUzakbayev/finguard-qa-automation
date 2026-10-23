from typing import Annotated

from fastapi import APIRouter, Header, Response

from app import services
from app.deps import CurrentUser, DbSession
from app.models import Transaction
from app.schemas import ErrorOut, TransferOut, TransferRequest

router = APIRouter(prefix="/api/transfers", tags=["transfers"])


@router.post(
    "",
    status_code=201,
    response_model=TransferOut,
    responses={
        200: {"model": TransferOut, "description": "Replay of an earlier request with the same Idempotency-Key"},
        401: {"model": ErrorOut},
        404: {"model": ErrorOut},
        409: {"model": ErrorOut},
        422: {"model": ErrorOut},
    },
)
def create_transfer(
    body: TransferRequest,
    user: CurrentUser,
    db: DbSession,
    response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=64)],
) -> Transaction:
    """Transfer money. The client must send a unique Idempotency-Key per logical transfer
    and reuse it when retrying, so that a retry never charges the customer twice."""
    tx, replayed = services.execute_transfer(db, user, body, idempotency_key)
    if replayed:
        response.status_code = 200
        response.headers["Idempotent-Replayed"] = "true"
    return tx
