from datetime import datetime

from pydantic import BaseModel, Field


class TokenRegisterRequest(BaseModel):
    device_token: str = Field(..., min_length=16, max_length=200)
    sip_extension: str = Field(..., min_length=1, max_length=20)
    app_bundle_id: str = Field(..., min_length=1, max_length=200)


class TokenRegisterResponse(BaseModel):
    id: int
    device_token: str
    sip_extension: str
    app_bundle_id: str
    created_at: str


class TokenDeleteRequest(BaseModel):
    device_token: str = Field(..., min_length=16, max_length=200)


class TokenInfo(BaseModel):
    id: int
    device_token: str
    app_bundle_id: str
    is_active: bool
    updated_at: str


class TokenListResponse(BaseModel):
    sip_extension: str
    tokens: list[TokenInfo]
    count: int


class HealthResponse(BaseModel):
    status: str
    sip_registered: bool
    apns_configured: bool
    active_tokens: int
    uptime_seconds: float
    version: str = "1.0.0"


class StatusResponse(BaseModel):
    sip_extension: str
    sip_registered: bool
    active_tokens: int
    recent_calls: list[dict]
    total_pushes_sent: int
    total_pushes_failed: int


class CallLogEntry(BaseModel):
    call_id: str
    caller: str
    caller_name: str
    callee_extension: str
    push_sent: bool
    push_result: str
    timestamp: str


class CallLogResponse(BaseModel):
    extension: str
    calls: list[CallLogEntry]
    total: int
    limit: int
    offset: int
