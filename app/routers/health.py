import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app import database as db
from app.config import settings
from app.models import HealthResponse, StatusResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["health"])

_start_time = time.time()
_bearer = HTTPBearer()


async def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> str:
    if credentials.credentials != settings.api_secret_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return credentials.credentials


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request):
    sip_client = request.app.state.sip_client
    sip_registered = sip_client.is_registered if sip_client else False
    apns_configured = bool(settings.apns_key_id and settings.apns_team_id)

    try:
        active_tokens = await db.get_active_token_count()
    except Exception:
        active_tokens = 0

    return HealthResponse(
        status="ok",
        sip_registered=sip_registered,
        apns_configured=apns_configured,
        active_tokens=active_tokens,
        uptime_seconds=round(time.time() - _start_time, 1),
    )


@router.get("/status", response_model=StatusResponse)
async def detailed_status(request: Request, _: str = Depends(verify_api_key)):
    sip_client = request.app.state.sip_client
    sip_registered = sip_client.is_registered if sip_client else False

    active_tokens = await db.get_active_token_count()
    sent, failed = await db.get_push_stats()
    calls, _ = await db.get_calls_for_extension(settings.sip_extension, limit=10)

    recent_calls = [
        {
            "call_id": c["call_id"],
            "caller": c["caller"],
            "push_sent": bool(c["push_sent"]),
            "push_result": c["push_result"],
            "timestamp": c["timestamp"],
        }
        for c in calls
    ]

    return StatusResponse(
        sip_extension=settings.sip_extension,
        sip_registered=sip_registered,
        active_tokens=active_tokens,
        recent_calls=recent_calls,
        total_pushes_sent=sent,
        total_pushes_failed=failed,
    )
