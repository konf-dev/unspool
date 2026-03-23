from fastapi import HTTPException, Request
from qstash import Receiver

from src.core.settings import get_settings
from src.telemetry.logger import get_logger

_log = get_logger("qstash_auth")


async def verify_qstash_signature(request: Request) -> None:
    settings = get_settings()
    signature = request.headers.get("Upstash-Signature")
    if not signature:
        raise HTTPException(status_code=403, detail="Missing Upstash-Signature header")

    body = await request.body()

    receiver = Receiver(
        current_signing_key=settings.QSTASH_CURRENT_SIGNING_KEY,
        next_signing_key=settings.QSTASH_NEXT_SIGNING_KEY,
    )

    # Reconstruct public URL for signature verification behind reverse proxy
    public_url = settings.API_URL.rstrip("/") + request.url.path

    try:
        receiver.verify(
            body=body.decode("utf-8"),
            signature=signature,
            url=public_url,
        )
    except Exception as exc:
        _log.warning(
            "qstash.signature_invalid",
            error=str(exc),
            public_url=public_url,
            request_url=str(request.url),
        )
        raise HTTPException(status_code=403, detail="Invalid QStash signature") from exc
