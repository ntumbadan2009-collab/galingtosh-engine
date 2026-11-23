"""Best-effort user notification after a confirmed, durable MP4 export.

The API key is server-only. It must never be exposed to Android, browser
bundles or a public edge function. Email delivery does not change render status.
"""
from __future__ import annotations

import html
import logging
import re
from typing import Any

import httpx

log = logging.getLogger("galingtosh.mail")


def _safe_sender(value: str) -> bool:
    """Only the project's verified domain may be used as the sender."""
    return bool(re.fullmatch(r"[A-Za-z0-9._%+-]+@galingtosh\.online", value.strip(), re.I))


def render_ready_message(title: str) -> tuple[str, str, str]:
    title = (title or "Votre vidéo").strip()[:140]
    subject = "Galingtosh — votre vidéo est prête"
    text = (
        "Bonjour,\n\n"
        f"Votre vidéo « {title} » est prête.\n"
        "Ouvrez votre espace Galingtosh pour la regarder et la télécharger :\n"
        "https://galingtosh.online/\n\n"
        "À bientôt,\nL'équipe Galingtosh"
    )
    safe_title = html.escape(title)
    markup = (
        '<div style="font-family:Arial,Helvetica,sans-serif;'
        'max-width:560px;margin:0 auto;padding:24px;color:#181225">'
        '<h1 style="font-size:24px">Galingtosh</h1>'
        '<p>Votre vidéo <strong>« ' + safe_title + ' »</strong> est prête.</p>'
        '<p>Retrouvez-la dans votre espace personnel.</p>'
        '<p><a href="https://galingtosh.online/" '
        'style="display:inline-block;background:#6c38ca;color:white;'
        'padding:12px 18px;border-radius:10px;text-decoration:none">'
        'Ouvrir mon studio</a></p>'
        '<p style="font-size:12px;color:#756b84">'
        'Ce message est lié à une production que vous avez demandée.</p>'
        '</div>'
    )
    return subject, text, markup


async def notify_render_ready(
    db: Any,
    job: dict[str, Any],
    title: str,
    *,
    api_key: str,
    from_address: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> bool:
    """Send once by job ID; return False when disabled or user is unverified.

    On SMTP/API failure raise an exception to be caught by the worker.
    Sending is intentionally not retried inside a render transaction.
    """
    if not api_key or not from_address:
        return False
    if not _safe_sender(from_address):
        raise ValueError("Adresse expéditrice Galingtosh non autorisée.")
    job_id = str(job.get("id") or "")
    user_id = str(job.get("user_id") or "")
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", job_id) or not re.fullmatch(r"[0-9a-fA-F-]{36}", user_id):
        return False

    recipient = await db.get_verified_user_email(user_id)
    if not recipient:
        return False
    subject, text, markup = render_ready_message(title)
    payload = {
        "from": f"Galingtosh <{from_address}>",
        "to": [recipient],
        "reply_to": "contact@galingtosh.online",
        "subject": subject,
        "text": text,
        "html": markup,
        "tags": [{"name": "type", "value": "render_ready"}],
    }
    async with httpx.AsyncClient(timeout=12, transport=transport) as client:
        response = await client.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Idempotency-Key": f"galingtosh-render-ready-{job_id}",
            },
            json=payload,
        )
    if response.status_code < 200 or response.status_code >= 300:
        # Avoid logging recipient, API token or a provider response with PII.
        raise RuntimeError(f"Resend refused transactional mail: HTTP {response.status_code}")
    log.info("Production email accepted for job %s", job_id)
    return True
