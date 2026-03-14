import asyncio
import logging
import uuid

from app import database as db
from app.config import settings
from app.push.apns_client import APNsService
from app.push.payload import build_voip_push_payload

logger = logging.getLogger(__name__)


class CallService:
    def __init__(self, apns: APNsService | None):
        self.apns = apns

    async def on_call_detected(self, call_data: dict) -> None:
        callee_ext = call_data.get("callee_extension", "")
        caller_number = call_data.get("caller_number", "Unknown")
        caller_name = call_data.get("caller_name", caller_number)
        call_id = call_data.get("call_id", "")

        logger.info(f"Processing call: {caller_name} ({caller_number}) -> {callee_ext}")

        # Look up push tokens for the target extension
        tokens = await db.get_tokens_for_extension(callee_ext)

        if not tokens:
            logger.warning(f"No push tokens for extension {callee_ext}")
            await db.log_call(call_id, caller_number, caller_name, callee_ext, False, "no_tokens")
            return

        if not self.apns:
            logger.error("APNs not configured, cannot send push")
            await db.log_call(call_id, caller_number, caller_name, callee_ext, False, "apns_not_configured")
            return

        call_uuid = str(uuid.uuid4())
        payload = build_voip_push_payload(
            caller_name=caller_name,
            caller_number=caller_number,
            call_id=call_id,
            call_uuid=call_uuid,
            sip_extension=callee_ext,
            asterisk_host=settings.asterisk_host,
        )

        # Send push to all registered devices in parallel
        tasks = [self.apns.send_voip_push(t["device_token"], payload) for t in tokens]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        any_success = False
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Push exception: {result}")
                continue
            if result.success:
                any_success = True
            elif result.should_deactivate:
                await db.deactivate_token(result.device_token)
                logger.info(f"Deactivated invalid token {result.device_token[:12]}...")

        push_result = "success" if any_success else "all_failed"
        await db.log_call(call_id, caller_number, caller_name, callee_ext, any_success, push_result)
        logger.info(f"Call processed: push_result={push_result} for {callee_ext}")
