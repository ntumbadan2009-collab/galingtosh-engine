import pytest
from app.storage.supabase import SupabaseError, validate_upload_path

def test_upload_path_must_be_under_user_folder():
    assert validate_upload_path("user-123/photos/a.jpg", "user-123") == "user-123/photos/a.jpg"

@pytest.mark.parametrize("path", ["../other/a.jpg","user-999/a.jpg","user-123/../x.jpg","/user-123/a.jpg"])
def test_rejects_unsafe_upload_paths(path):
    with pytest.raises(SupabaseError):
        validate_upload_path(path, "user-123")
