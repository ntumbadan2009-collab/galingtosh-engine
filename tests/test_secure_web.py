import asyncio
import pytest
from PIL import Image
from app.media.secure_web import identify,clean_image,digest,download_extended
from app.media.ffmpeg import decoder_env,local_inputs
from app.media.resolver import download_public_media,UnsafeMediaURL

def test_disallow_html_playlist_and_zip(tmp_path):
    source=tmp_path/"raw"
    for payload in [b"<html>not a movie",b"#EXTM3U\nhttp://example.com",b"PK\x03\x04zip"]:
        source.write_bytes(payload)
        with pytest.raises(ValueError): identify(source,"video","video/mp4")
        with pytest.raises(ValueError): identify(source,"image","image/jpeg")

def test_image_reencode_and_hash(tmp_path):
    source=tmp_path/"raw.png";out=tmp_path/"clean.jpg"
    Image.new("RGB",(100,50),"red").save(source)
    identify(source,"image","image/png")
    clean_image(source,out,48)
    with Image.open(out) as img: assert img.format=="JPEG" and img.width==48
    assert len(digest(source))==64

def test_decoder_has_no_api_secrets(monkeypatch):
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY","secret")
    assert "SUPABASE_SERVICE_ROLE_KEY" not in decoder_env()
    assert local_inputs(["-i","file.mp4"])==["-protocol_whitelist","file,pipe","-i","file.mp4"]

def test_quarantine_and_host_gate(tmp_path,monkeypatch):
    monkeypatch.setenv("SECURE_WEB_MEDIA_ENABLED","false")
    with pytest.raises(ValueError):
        asyncio.run(download_extended({"kind":"image","provenance":{"source":"archive"}},tmp_path/"raw"))
    with pytest.raises(UnsafeMediaURL):
        asyncio.run(download_public_media("https://archive.org.evil.example/x",tmp_path/"raw",allowed_hosts=("archive.org",)))

def test_web_license_is_asset_specific_and_same_origin():
    import json
    from app.media.licensed_web import extract_candidates
    data={"@type":"ImageObject","name":"Actual photograph","creator":{"name":"Author"},"contentUrl":"https://example.org/media/photo.jpg","license":"https://creativecommons.org/licenses/by/4.0/"}
    page=lambda x:'<script type="application/ld+json">'+json.dumps(x)+'</script>'
    out=extract_candidates(page(data),"https://example.org/story","image")
    assert len(out)==1 and out[0]["license"]=="CC BY 4.0"
    assert not extract_candidates(page({**data,"license":"https://creativecommons.org/licenses/by-nc/4.0/"}),"https://example.org/story","image")
    assert not extract_candidates(page({**data,"contentUrl":"https://other.example/media.jpg"}),"https://example.org/story","image")
    assert not extract_candidates(page({"@type":"Article","license":data["license"],"image":{k:v for k,v in data.items() if k!="license"}}),"https://example.org/story","image")
    assert not extract_candidates(page({"@type":"ImageObject","name":"image","contentUrl":"https://example.org/a.jpg"}),"https://example.org/story","image")
