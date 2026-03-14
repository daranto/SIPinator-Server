import asyncio
import logging
import socket

from pyVoIP.VoIP import CallState, InvalidStateError, PhoneStatus, VoIPPhone

logger = logging.getLogger(__name__)


def detect_local_ip(target_host: str) -> str:
    """Detect local IP by opening a UDP socket toward the target."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((target_host, 1))
        ip = s.getsockname()[0]
        s.close()
        logger.info(f"Auto-detected local IP: {ip}")
        return ip
    except Exception:
        logger.warning("Could not auto-detect local IP, falling back to 0.0.0.0")
        return "0.0.0.0"


class SIPClient:
    def __init__(
        self,
        asterisk_host: str,
        asterisk_port: int,
        username: str,
        password: str,
        local_ip: str,
        local_port: int,
        on_call_callback,
    ):
        self.asterisk_host = asterisk_host
        self.asterisk_port = asterisk_port
        self.username = username
        self.password = password
        self.local_ip = local_ip or detect_local_ip(asterisk_host)
        self.local_port = local_port
        self.on_call_callback = on_call_callback
        self.phone: VoIPPhone | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def is_registered(self) -> bool:
        if self.phone:
            return self.phone.get_status() == PhoneStatus.REGISTERED
        return False

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self.phone = VoIPPhone(
            server=self.asterisk_host,
            port=self.asterisk_port,
            username=self.username,
            password=self.password,
            callCallback=self._handle_incoming_call,
            myIP=self.local_ip,
            sipPort=self.local_port,
            rtpPortLow=10000,
            rtpPortHigh=10010,
        )
        self.phone.start()
        logger.info(
            f"SIP client started: {self.username}@{self.asterisk_host}:{self.asterisk_port}"
        )

    def stop(self) -> None:
        if self.phone:
            try:
                self.phone.stop()
            except Exception as e:
                logger.warning(f"SIP stop error: {e}")
            logger.info("SIP client stopped")

    @staticmethod
    def _get_header(headers: dict, name: str, default: str = "") -> str:
        """Safely extract a SIP header value regardless of type."""
        val = headers.get(name, default)
        if val is None:
            return default
        if isinstance(val, list):
            val = val[0] if val else default
        if isinstance(val, dict):
            return val.get("raw", val.get("value", str(val)))
        if hasattr(val, "raw"):
            return str(val.raw)
        return str(val)

    def _handle_incoming_call(self, call) -> None:
        """Called by pyVoIP in its SIP thread when INVITE arrives."""
        try:
            request = call.request
            headers = getattr(request, "headers", {})

            from_h = headers.get("From", {})
            to_h = headers.get("To", {})
            call_id = self._get_header(headers, "Call-ID")

            # pyVoIP provides parsed dict with: number, caller, address, host
            if isinstance(from_h, dict):
                caller_number = from_h.get("number", "")
                caller_name = from_h.get("caller", "") or caller_number
            else:
                caller_number = str(from_h)
                caller_name = caller_number

            if isinstance(to_h, dict):
                callee_ext = to_h.get("number", "")
            else:
                callee_ext = str(to_h)

            # X-Original-Extension from Asterisk dialplan overrides To
            x_ext = self._get_header(headers, "X-Original-Extension").strip()
            if x_ext:
                callee_ext = x_ext

            call_data = {
                "caller_number": caller_number,
                "caller_name": caller_name,
                "callee_extension": callee_ext,
                "call_id": call_id,
            }

            logger.info(
                f"Incoming call: {call_data['caller_name']} ({call_data['caller_number']}) "
                f"-> {call_data['callee_extension']}"
            )

            # Deny immediately - we only need to trigger the push
            try:
                call.deny()
            except (InvalidStateError, Exception):
                pass

            # Bridge to async event loop for push notification
            if self._loop and self.on_call_callback:
                asyncio.run_coroutine_threadsafe(
                    self.on_call_callback(call_data), self._loop
                )

        except Exception as e:
            logger.error(f"Error handling incoming call: {e}", exc_info=True)
            try:
                call.deny()
            except Exception:
                pass
