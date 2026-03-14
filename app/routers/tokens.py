import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app import database as db
from app.models import (
    CallLogEntry,
    CallLogResponse,
    TokenDeleteRequest,
    TokenInfo,
    TokenListResponse,
    TokenRegisterRequest,
    TokenRegisterResponse,
)
from app.routers.health import verify_api_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["tokens"])


@router.post("/tokens", response_model=TokenRegisterResponse, status_code=201)
async def register_token(
    req: TokenRegisterRequest, _: str = Depends(verify_api_key)
):
    row = await db.upsert_token(req.sip_extension, req.device_token, req.app_bundle_id)
    logger.info(f"Token registered for extension {req.sip_extension}")
    return TokenRegisterResponse(
        id=row["id"],
        device_token=row["device_token"],
        sip_extension=row["sip_extension"],
        app_bundle_id=row["app_bundle_id"],
        created_at=row["created_at"],
    )


@router.delete("/tokens")
async def delete_token(req: TokenDeleteRequest, _: str = Depends(verify_api_key)):
    deleted = await db.delete_token(req.device_token)
    if not deleted:
        raise HTTPException(status_code=404, detail="Token not found")
    logger.info(f"Token deleted: {req.device_token[:12]}...")
    return {"message": "Token unregistered"}


@router.get("/tokens/{sip_extension}", response_model=TokenListResponse)
async def list_tokens(sip_extension: str, _: str = Depends(verify_api_key)):
    tokens = await db.get_tokens_for_extension(sip_extension)
    return TokenListResponse(
        sip_extension=sip_extension,
        tokens=[
            TokenInfo(
                id=t["id"],
                device_token=t["device_token"][:12] + "...",
                app_bundle_id=t["app_bundle_id"],
                is_active=bool(t["is_active"]),
                updated_at=t["updated_at"],
            )
            for t in tokens
        ],
        count=len(tokens),
    )


@router.get("/extensions/{extension}/calls", response_model=CallLogResponse)
async def get_call_log(
    extension: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: str = Depends(verify_api_key),
):
    calls, total = await db.get_calls_for_extension(extension, limit, offset)
    return CallLogResponse(
        extension=extension,
        calls=[
            CallLogEntry(
                call_id=c["call_id"] or "",
                caller=c["caller"] or "",
                caller_name=c["caller_name"] or "",
                callee_extension=c["callee_extension"] or "",
                push_sent=bool(c["push_sent"]),
                push_result=c["push_result"] or "",
                timestamp=c["timestamp"] or "",
            )
            for c in calls
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
