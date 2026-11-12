import pytest
from app.media.resolver import UnsafeMediaURL, validate_remote_url

@pytest.mark.parametrize("url", ["http://127.0.0.1/x","http://10.1.2.3/x",
 "http://169.254.169.254/latest","http://[::1]/","file:///etc/passwd",
 "http://localhost/x","http://u:p@example.com/x","http://example.com:8080/x"])
def test_rejects_unsafe_urls(url):
    with pytest.raises(UnsafeMediaURL):
        validate_remote_url(url)

def test_accepts_public_https_url():
    assert validate_remote_url("https://example.com/a.mp4") == "https://example.com/a.mp4"
