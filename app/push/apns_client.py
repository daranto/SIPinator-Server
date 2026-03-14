import logging
from dataclasses import dataclass

from aioapns import APNs, NotificationRequest, PushType

logger = logging.getLogger(__name__)


@dataclass
class PushResult:
    success: bool
    device_token: str
    reason: str = ""
    should_deactivate: bool = False


class APNsService:
    def __init__(
        self,
        key_path: str,
        key_id: str,
        team_id: str,
        topic: str,
        use_sandbox: bool = True,
    ):
        self.topic = topic
        self.client = APNs(
            key=key_path,
            key_id=key_id,
            team_id=team_id,
            topic=topic,
            use_sandbox=use_sandbox,
        )
        logger.info(f"APNs client initialized (topic={topic}, sandbox={use_sandbox})")

    async def send_voip_push(
        self, device_token: str, payload: dict
    ) -> PushResult:
        request = NotificationRequest(
            device_token=device_token,
            message=payload,
            push_type=PushType.VOIP,
        )
        try:
            response = await self.client.send_notification(request)
            if response.is_successful:
                logger.info(f"VoIP push sent to {device_token[:12]}...")
                return PushResult(success=True, device_token=device_token)

            reason = response.description or "unknown"
            should_deactivate = reason in (
                "BadDeviceToken",
                "Unregistered",
                "ExpiredToken",
            )
            logger.warning(f"VoIP push failed for {device_token[:12]}...: {reason}")
            return PushResult(
                success=False,
                device_token=device_token,
                reason=reason,
                should_deactivate=should_deactivate,
            )
        except Exception as e:
            logger.error(f"APNs send error: {e}")
            return PushResult(
                success=False,
                device_token=device_token,
                reason=str(e),
            )
