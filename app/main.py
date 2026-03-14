import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import database as db
from app.config import settings
from app.push.apns_client import APNsService
from app.routers import health, tokens
from app.services.call_service import CallService
from app.sip.client import SIPClient

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    logger.info("SIPinator Server starting...")

    # Database
    os.makedirs(os.path.dirname(settings.database_path), exist_ok=True)
    await db.init_db(settings.database_path)

    # APNs
    apns: APNsService | None = None
    if settings.apns_key_id and settings.apns_team_id and settings.apns_bundle_id:
        try:
            apns = APNsService(
                key_path=settings.apns_key_path,
                key_id=settings.apns_key_id,
                team_id=settings.apns_team_id,
                topic=settings.apns_topic,
                use_sandbox=settings.apns_use_sandbox,
            )
        except Exception as e:
            logger.error(f"APNs initialization failed: {e}")
    else:
        logger.warning("APNs not configured (missing key_id/team_id/bundle_id)")

    # Call Service
    call_service = CallService(apns=apns)

    # SIP Client
    sip_client: SIPClient | None = None
    loop = asyncio.get_running_loop()

    if settings.sip_password:
        try:
            sip_client = SIPClient(
                asterisk_host=settings.asterisk_host,
                asterisk_port=settings.asterisk_port,
                username=settings.sip_username,
                password=settings.sip_password,
                local_ip=settings.sip_local_ip,
                local_port=settings.sip_local_port,
                on_call_callback=call_service.on_call_detected,
            )
            sip_client.start(loop)
        except Exception as e:
            logger.error(f"SIP client start failed: {e}")
            sip_client = None
    else:
        logger.warning("SIP not configured (no password set)")

    # Store references on app state
    app.state.sip_client = sip_client
    app.state.call_service = call_service
    app.state.apns = apns

    logger.info("SIPinator Server ready")
    yield

    # --- Shutdown ---
    logger.info("SIPinator Server shutting down...")
    if sip_client:
        sip_client.stop()
    await db.close_db()
    logger.info("SIPinator Server stopped")


app = FastAPI(
    title="SIPinator Server",
    description="SIP-to-Push-Notification Bridge for iOS VoIP Apps",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(tokens.router)
