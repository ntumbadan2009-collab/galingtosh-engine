import json
import uuid

import httpx
import pytest

from app.notifications.resend import notify_render_ready, render_ready_message


class FakeDb:
    def __init__(self, email="verified@example.com"):
        self.email = email
        self.calls = []

    async def get_verified_user_email(self, user_id):
        self.calls.append(user_id)
        return self.email


@pytest.mark.asyncio
async def test_render_ready_notification_uses_verified_recipient_and_durable_link():
    payloads = []
    headers = []
    def handler(request):
        payloads.append(json.loads(request.content))
        headers.append(dict(request.headers))
        return httpx.Response(200, json={"id": "message-123"})

    job_id, user_id = str(uuid.uuid4()), str(uuid.uuid4())
    db = FakeDb()
    success = await notify_render_ready(
        db, {"id": job_id, "user_id": user_id}, 'Un <film> & ses secrets',
        api_key="re_test", from_address="notifications@galingtosh.online",
        transport=httpx.MockTransport(handler),
    )
    assert success is True
    assert db.calls == [user_id]
    assert payloads[0]["to"] == ["verified@example.com"]
    assert payloads[0]["reply_to"] == "contact@galingtosh.online"
    assert "Un &lt;film&gt; &amp; ses secrets" in payloads[0]["html"]
    assert "https://galingtosh.online/" in payloads[0]["text"]
    assert headers[0]["idempotency-key"] == f"galingtosh-render-ready-{job_id}"


@pytest.mark.asyncio
async def test_disabled_or_unverified_address_cannot_send():
    db = FakeDb()
    job = {"id": str(uuid.uuid4()), "user_id": str(uuid.uuid4())}
    assert await notify_render_ready(db, job, "Film", api_key="", from_address="notifications@galingtosh.online") is False
    assert db.calls == []
    db.email = None
    assert await notify_render_ready(db, job, "Film", api_key="re_test", from_address="notifications@galingtosh.online") is False


@pytest.mark.asyncio
async def test_rejects_external_sender():
    with pytest.raises(ValueError):
        await notify_render_ready(
            FakeDb(), {"id": str(uuid.uuid4()), "user_id": str(uuid.uuid4())},
            "Film", api_key="re_test", from_address="malicious@other-domain.com"
        )


@pytest.mark.asyncio
async def test_delivery_http_error_does_not_leak_credentials():
    def handler(request):
        return httpx.Response(403, json={"message": "sender rejected"})
    with pytest.raises(RuntimeError, match="HTTP 403") as error:
        await notify_render_ready(
            FakeDb(), {"id": str(uuid.uuid4()), "user_id": str(uuid.uuid4())},
            "Film", api_key="re_topsecret", from_address="notifications@galingtosh.online",
            transport=httpx.MockTransport(handler),
        )
    assert "topsecret" not in str(error.value)


def test_message_is_readable_and_short():
    subject, plain, markup = render_ready_message("Mon film")
    assert subject and "Mon film" in plain and "Mon film" in markup
