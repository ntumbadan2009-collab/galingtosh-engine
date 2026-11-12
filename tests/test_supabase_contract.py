import pytest
from app.storage.supabase import SupabaseREST, SupabaseError, validate_upload_path

def test_upload_path_is_scoped_to_user():
    assert validate_upload_path("user-1/media/photo.jpg","user-1") == "user-1/media/photo.jpg"

@pytest.mark.parametrize("path", ["", "/user-1/a.jpg", "user-2/a.jpg", "user-1/../secret", "user-1//a.jpg", "user-1/a.jpg/"])
def test_upload_path_rejects_escape(path):
    with pytest.raises(SupabaseError):
        validate_upload_path(path,"user-1")

@pytest.mark.asyncio
async def test_patch_job_rejects_protected_columns():
    db=SupabaseREST("https://example.supabase.co","not-a-real-key")
    with pytest.raises(SupabaseError):
        await db.patch_render_job("job-1",{"user_id":"attacker"})
    with pytest.raises(SupabaseError):
        await db.patch_render_job("job-1",{"project_id":"other"})
