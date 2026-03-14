import time
import uuid


def build_voip_push_payload(
    caller_name: str,
    caller_number: str,
    call_uuid: str | None = None,
    sip_extension: str = "",
    asterisk_host: str = "",
) -> dict:
    if call_uuid is None:
        call_uuid = str(uuid.uuid4())

    return {
        "aps": {},
        "caller_id": caller_number,
        "caller_name": caller_name or caller_number,
        "call_uuid": call_uuid,
        "sip_extension": sip_extension,
        "server_host": asterisk_host,
        "timestamp": int(time.time()),
    }
