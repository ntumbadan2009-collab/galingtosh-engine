"""Durable per-scene render checkpoints stored in a private Supabase bucket.

Scene artifacts are uploaded *before* a manifest is committed. An interrupted
upload is not considered a checkpoint. Invalid or incompatible entries simply
cause that scene to be encoded again, never trusted blindly.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from app.storage.supabase import SupabaseREST

logger = logging.getLogger("galingtosh.checkpoints")
MAX_SEGMENT_BYTES = 49 * 1024 * 1024
CHECKPOINT_FORMAT = 1


def fingerprint(data: Any) -> str:
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class SceneCheckpoints:
    def __init__(self, db: SupabaseREST, user_id: str, project_id: str, job_id: str) -> None:
        self.db = db
        # These are server-side UUIDs read from the claimed render job, never
        # arbitrary file paths provided by a browser.
        import uuid
        self.base = "/".join(str(uuid.UUID(str(item))) for item in (user_id, project_id, job_id))
        self.bucket = "temp-assets"

    def prefix(self, index: int, signature: str) -> str:
        if index < 0 or len(signature) != 64 or any(c not in "0123456789abcdef" for c in signature):
            raise ValueError("Invalid checkpoint identifier")
        return f"{self.base}/scenes/v{CHECKPOINT_FORMAT}/{index:04d}/{signature}"

    async def restore(self, index: int, signature: str, work: Path) -> list[dict] | None:
        prefix = self.prefix(index, signature)
        downloaded: list[Path] = []
        try:
            manifest_bytes = await self.db.download_storage_bytes(self.bucket, prefix + "/manifest.json", max_bytes=64 * 1024)
            manifest = json.loads(manifest_bytes)
            if (manifest.get("version") != CHECKPOINT_FORMAT or
                    manifest.get("signature") != signature or
                    not isinstance(manifest.get("segments"), list) or
                    not 1 <= len(manifest["segments"]) <= 150):
                return None
            entries: list[dict] = []
            for item in manifest["segments"]:
                name = item.get("name")
                checksum = item.get("sha256")
                size = item.get("size")
                duration = item.get("duration")
                if (not isinstance(name, str) or not name.startswith("segment_") or
                        not name.endswith(".mp4") or "/" in name or "\\" in name or
                        not isinstance(size, int) or size <= 0 or size > MAX_SEGMENT_BYTES or
                        not isinstance(duration, (int, float)) or duration <= 0 or
                        not isinstance(checksum, str) or len(checksum) != 64):
                    return None
                target = work / name
                downloaded.append(target)
                await self.db.download_storage_file(self.bucket, prefix + "/" + name, target, max_bytes=size)
                if target.stat().st_size != size or sha256_file(target) != checksum:
                    raise ValueError("Checkpoint integrity mismatch")
                entries.append({"name": name, "shot_id": item.get("shot_id"), "duration": float(duration)})
            logger.info("restored scene=%s segments=%s", index + 1, len(entries))
            return entries
        except Exception as exc:
            logger.warning("scene checkpoint unavailable index=%s: %s", index, type(exc).__name__)
            # A partial restore must not leave corrupt scene files behind.
            for file in downloaded:
                file.unlink(missing_ok=True)
            return None

    async def save(self, index: int, signature: str, entries: list[dict], work: Path) -> bool:
        prefix = self.prefix(index, signature)
        try:
            manifest = {"version": CHECKPOINT_FORMAT, "signature": signature, "segments": []}
            for entry in entries:
                path = work / entry["name"]
                size = path.stat().st_size
                if not 0 < size <= MAX_SEGMENT_BYTES:
                    logger.warning("checkpoint skipped: scene %s segment too large or empty", index + 1)
                    return False
                await self.db.upload_file(self.bucket, prefix + "/" + path.name, path, "video/mp4")
                manifest["segments"].append({
                    "name": path.name, "sha256": sha256_file(path), "size": size,
                    "shot_id": entry.get("shot_id"), "duration": float(entry["duration"]),
                })
            if not manifest["segments"]:
                return False
            await self.db.upload_storage_bytes(
                self.bucket, prefix + "/manifest.json",
                json.dumps(manifest, ensure_ascii=False).encode(), "application/json",
            )
            logger.info("checkpoint committed scene=%s segments=%s", index + 1, len(entries))
            return True
        except Exception:
            logger.exception("checkpoint save unavailable; scene remains encoded locally index=%s", index)
            return False
