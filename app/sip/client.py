import asyncio
import logging
import re
import socket

from pyVoIP.VoIP import CallState, InvalidStateError, PhoneStatus, VoIPPhone

logger = logging.getLogger(__name__)


def parse_sip_from(header: str) -> dict:
    """Parse SIP From/To header into display_name, uri, username."""
    display_name = ""
    username = ""
    uri = ""

    # Extract display name: "Name" <sip:...> or Name <sip:...>
    name_match = re.match(r'"?([^"<]*?)"?\s*<', header)
    if name_match:
        display_name = name_match.group(1).strip()

    # Extract URI
    uri_match = re.search(r"<(sip:[^>]+)>", header)
    if uri_match:
        uri = uri_match.group(1)
    elif "sip:" in header:
        uri = header.split(";")[0].strip()

    # Extract username from sip:user@host
    user_match = re.search(r"sip:([^@]+)@", uri or header)
    if user_match:
        username = user_match.group(1)

    return {"display_name": display_name, "uri": uri, "username": username}


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
        """Safely extract a SIP header value regardless of type (str or list)."""
        val = headers.get(name, default)
        if isinstance(val, list):
            return val[0] if val else default
        return str(val) if val else default

    def _handle_incoming_call(self, call) -> None:
        """Called by pyVoIP in its SIP thread when INVITE arrives."""
        try:
            request = call.request
            headers = getattr(request, "headers", {})

            from_header = self._get_header(headers, "From")
            to_header = self._get_header(headers, "To")
            call_id = self._get_header(headers, "Call-ID")

            # Check for X-Original-Extension header (set by Asterisk dialplan)
            x_ext = self._get_header(headers, "X-Original-Extension").strip()

            caller_info = parse_sip_from(from_header)
            to_info = parse_sip_from(to_header)

            call_data = {
                "caller_number": caller_info["username"],
                "caller_name": caller_info["display_name"] or caller_info["username"],
                "callee_extension": x_ext or to_info["username"],
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
