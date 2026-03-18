from fastapi import HTTPException, Request
from qstash import Receiver

from src.config import get_settings
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

    # QStash signs against the public URL it dispatched to (e.g. https://api.unspool.life/jobs/...).
    # Behind Railway's reverse proxy, request.url shows the internal URL (http://0.0.0.0:PORT/...).
    # Reconstruct the public URL so signature verification matches.
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
