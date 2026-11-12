import httpx
import pytest
from app.storage.supabase import SupabaseREST

@pytest.mark.asyncio
async def test_claim_empty_and_job_patch_contract():
    calls = []
    async def handler(request):
        calls.append(request)
        if request.url.path.endswith("/rpc/claim_render_job"):
            return httpx.Response(200, json=[])
        if request.method == "PATCH":
            return httpx.Response(204)
        return httpx.Response(200, json=[])
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    db = SupabaseREST("https://example.supabase.co", "test-secret", client=client)
    assert await db.claim_render_job("worker-a") is None
    await db.patch_render_job("job-1", {"progress": 20})
    assert calls[0].headers["authorization"] == "Bearer test-secret"
    assert calls[0].json() == {"p_worker_id": "worker-a"}
    assert calls[1].method == "PATCH"
    assert calls[1].url.params["id"] == "eq.job-1"
    await client.aclose()

@pytest.mark.asyncio
async def test_patch_rejects_forbidden_columns():
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(204)))
    db = SupabaseREST("https://example.supabase.co", "secret", client=client)
    with pytest.raises(ValueError):
        await db.patch_render_job("job", {"user_id": "other-user"})
    await client.aclose()

@pytest.mark.asyncio
async def test_upload_restricts_buckets_and_paths():
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})))
    db = SupabaseREST("https://example.supabase.co", "secret", client=client)
    with pytest.raises(ValueError):
        await db.upload_object("user-uploads", "x.mp4", b"x", "video/mp4")
    with pytest.raises(ValueError):
        await db.upload_object("renders", "../escape.mp4", b"x", "video/mp4")
    await client.aclose()
