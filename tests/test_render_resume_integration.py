"""Exercise a genuine FFmpeg scene restart with a private-storage adapter.

The first render deliberately raises asyncio.CancelledError after persisting
scene 1, representing a worker termination. The second run must fetch the
stored scene instead of producing it again, and finish an MP4.
"""
import asyncio
from pathlib import Path

import pytest
from app.core.renderer import FilmRenderer
from app.core.checkpoints import SceneCheckpoints, fingerprint


class TestStorage:
    def __init__(self):
        self.items = {}

    async def upload_file(self, bucket, key, path, content_type):
        self.items[(bucket, key)] = Path(path).read_bytes()

    async def upload_storage_bytes(self, bucket, key, payload, content_type):
        self.items[(bucket, key)] = bytes(payload)

    async def download_storage_bytes(self, bucket, key, max_bytes=65536):
        return self.items[(bucket, key)]

    async def download_storage_file(self, bucket, key, destination, max_bytes):
        content = self.items[(bucket, key)]
        assert len(content) <= max_bytes
        Path(destination).write_bytes(content)


class InterruptedOnce(SceneCheckpoints):
    def __init__(self, store):
        super().__init__(store,
                         "11111111-1111-4111-8111-111111111111",
                         "22222222-2222-4222-8222-222222222222",
                         "33333333-3333-4333-8333-333333333333")
        self.injected = False

    async def save(self, index, signature, entries, work):
        result = await super().save(index, signature, entries, work)
        if index == 0 and result and not self.injected:
            self.injected = True
            raise asyncio.CancelledError("simulated engine shutdown after checkpoint")
        return result


@pytest.mark.asyncio
async def test_render_resumes_after_engine_shutdown(tmp_path):
    film = {
        "info": {"title": "Checkpoint E2E test"},
        "format": {"aspect": "16:9", "fps": 24},
        "render": {"resolution": "720p"},
        "scenes": [
            {"id": "s1", "order": 1, "durationSec": 1,
             "shots": [{"id": "p1", "order": 1, "inSec": 0, "outSec": 1}]},
            {"id": "s2", "order": 2, "durationSec": 1,
             "shots": [{"id": "p2", "order": 1, "inSec": 0, "outSec": 1}]},
        ],
    }
    store = TestStorage()
    checkpoints = InterruptedOnce(store)
    renderer = FilmRenderer(max_seconds=10, max_output_mb=10)

    with pytest.raises(asyncio.CancelledError):
        await renderer.render(film, {}, tmp_path / "interrupted.mp4", checkpoints=checkpoints)
    assert checkpoints.injected
    assert any(key.endswith("/manifest.json") for bucket, key in store.items if bucket == "temp-assets")

    fresh_renderer = FilmRenderer(max_seconds=10, max_output_mb=10)
    encoded = []
    original_black = fresh_renderer._black

    async def record_black(destination, *args, **kwargs):
        encoded.append(destination.name)
        return await original_black(destination, *args, **kwargs)

    fresh_renderer._black = record_black
    result = await fresh_renderer.render(film, {}, tmp_path / "resumed.mp4", checkpoints=checkpoints)
    assert encoded == ["segment_0001.mp4"], "First scene should have been restored, not encoded again"
    assert result["duration_seconds"] >= 1.9
    assert (tmp_path / "resumed.mp4").stat().st_size > 100
