"""Unit tests for durable checkpoint uploads, integrity and safe resumption."""
import json
from pathlib import Path
import pytest

from app.core.checkpoints import SceneCheckpoints, fingerprint


class MemoryStorage:
    def __init__(self):
        self.objects = {}

    async def upload_file(self, bucket, key, path, content_type):
        self.objects[(bucket, key)] = Path(path).read_bytes()

    async def upload_storage_bytes(self, bucket, key, content, content_type):
        self.objects[(bucket, key)] = bytes(content)

    async def download_storage_bytes(self, bucket, key, max_bytes=65536):
        blob = self.objects[(bucket, key)]
        assert len(blob) <= max_bytes
        return blob

    async def download_storage_file(self, bucket, key, destination, max_bytes):
        blob = self.objects[(bucket, key)]
        if len(blob) > max_bytes:
            raise ValueError("oversized segment")
        Path(destination).write_bytes(blob)


@pytest.fixture
def checkpoint():
    db = MemoryStorage()
    user = "11111111-1111-4111-8111-111111111111"
    project = "22222222-2222-4222-8222-222222222222"
    job = "33333333-3333-4333-8333-333333333333"
    return SceneCheckpoints(db, user, project, job)


@pytest.mark.asyncio
async def test_scene_checkpoint_roundtrip(checkpoint, tmp_path):
    source = tmp_path / "one"
    restored = tmp_path / "two"
    source.mkdir()
    restored.mkdir()
    (source / "segment_0000.mp4").write_bytes(b"synthetic segment alpha")
    (source / "segment_0001.mp4").write_bytes(b"synthetic segment beta")
    signature = fingerprint({"film": "one", "version": 2})
    scene = [
        {"name": "segment_0000.mp4", "shot_id": "a", "duration": 2.5},
        {"name": "segment_0001.mp4", "shot_id": "b", "duration": 3.5},
    ]
    assert await checkpoint.save(0, signature, scene, source)
    loaded = await checkpoint.restore(0, signature, restored)
    assert loaded == scene
    assert (restored / "segment_0000.mp4").read_bytes() == b"synthetic segment alpha"
    assert (restored / "segment_0001.mp4").read_bytes() == b"synthetic segment beta"


@pytest.mark.asyncio
async def test_manifest_missing_or_signature_changed_forces_reencode(checkpoint, tmp_path):
    sig = fingerprint({"version": 1})
    different = fingerprint({"version": 2})
    assert await checkpoint.restore(0, sig, tmp_path) is None
    path = tmp_path / "segment_0000.mp4"
    path.write_bytes(b"original")
    assert await checkpoint.save(0, sig, [{"name": path.name, "duration": 1, "shot_id": None}], tmp_path)
    assert await checkpoint.restore(0, different, tmp_path) is None


@pytest.mark.asyncio
async def test_corrupted_checkpoint_removed_and_reencoded(checkpoint, tmp_path):
    source = tmp_path / "source"
    restore = tmp_path / "restored"
    source.mkdir()
    restore.mkdir()
    path = source / "segment_0000.mp4"
    path.write_bytes(b"original")
    sig = fingerprint({"film": "unchanged"})
    assert await checkpoint.save(0, sig, [{"name": path.name, "duration": 2, "shot_id": "a"}], source)
    key = checkpoint.prefix(0, sig) + "/segment_0000.mp4"
    checkpoint.db.objects[("temp-assets", key)] = b"tampered"
    assert await checkpoint.restore(0, sig, restore) is None
    assert not (restore / "segment_0000.mp4").exists()


@pytest.mark.asyncio
async def test_manifest_only_written_after_all_segments(checkpoint, tmp_path):
    sig = fingerprint({"job": "upload-failure"})
    (tmp_path / "segment_0000.mp4").write_bytes(b"short")
    manifest = checkpoint.prefix(0, sig) + "/manifest.json"
    result = await checkpoint.save(0, sig, [
        {"name": "segment_0000.mp4", "duration": 1, "shot_id": "a"},
        {"name": "segment_0001.mp4", "duration": 1, "shot_id": "b"},
    ], tmp_path)
    assert not result
    assert ("temp-assets", manifest) not in checkpoint.db.objects

@pytest.mark.asyncio
async def test_checkpoint_rejects_late_bad_entry_without_partial_restore(checkpoint,tmp_path):
    sig=fingerprint({"test":"late_bad_entry"})
    source=tmp_path/"source";source.mkdir()
    work=tmp_path/"restore";work.mkdir()
    (source/"segment_0000.mp4").write_bytes(b"one")
    (source/"segment_0001.mp4").write_bytes(b"two")
    assert await checkpoint.save(0,sig,[{"name":"segment_0000.mp4","duration":1},{"name":"segment_0001.mp4","duration":1}],source)
    manifest=("temp-assets",checkpoint.prefix(0,sig)+"/manifest.json")
    obj=json.loads(checkpoint.db.objects[manifest])
    obj["segments"][1]["duration"]=float("nan")
    checkpoint.db.objects[manifest]=json.dumps(obj).encode()
    assert await checkpoint.restore(0,sig,work) is None
    assert not list(work.iterdir())

@pytest.mark.asyncio
async def test_checkpoint_does_not_overwrite_previous_scene(checkpoint,tmp_path):
    sig=fingerprint({"test":"collision"})
    source=tmp_path/"source";source.mkdir()
    work=tmp_path/"restore";work.mkdir()
    (source/"segment_0000.mp4").write_bytes(b"cached")
    (work/"segment_0000.mp4").write_bytes(b"previous scene")
    assert await checkpoint.save(0,sig,[{"name":"segment_0000.mp4","duration":1}],source)
    assert await checkpoint.restore(0,sig,work) is None
    assert (work/"segment_0000.mp4").read_bytes()==b"previous scene"
