"""Durable per-scene render checkpoints stored in a private Supabase bucket.

Scene artifacts are uploaded *before* a manifest is committed. An interrupted
upload is not considered a checkpoint. Invalid or incompatible entries simply
cause that scene to be encoded again, never trusted blindly.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import tempfile
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
        committed: list[Path] = []
        success = False
        try:
            manifest_bytes = await self.db.download_storage_bytes(self.bucket, prefix + "/manifest.json", max_bytes=64 * 1024)
            manifest = json.loads(manifest_bytes)
            if (manifest.get("version") != CHECKPOINT_FORMAT or manifest.get("signature") != signature or
                    not isinstance(manifest.get("segments"), list) or not 1 <= len(manifest["segments"]) <= 150):
                return None
            entries: list[dict] = []
            seen = set()
            # Validate every entry before downloading anything. Never replace an
            # existing segment from an earlier scene, even on corrupt manifests.
            for item in manifest["segments"]:
                name, checksum, size, duration = (item.get(k) for k in ("name","sha256","size","duration"))
                if (not isinstance(name,str) or not re.fullmatch(r"segment_[A-Za-z0-9_]+\.mp4",name) or
                    name in seen or (work/name).exists() or type(size) is not int or not 0<size<=MAX_SEGMENT_BYTES or
                    type(duration) not in (int,float) or not math.isfinite(duration) or duration<=0 or
                    not isinstance(checksum,str) or not re.fullmatch(r"[0-9a-f]{64}",checksum)):
                    return None
                seen.add(name)
                entries.append({"name":name,"shot_id":item.get("shot_id"),"duration":float(duration)})
            with tempfile.TemporaryDirectory(prefix="restore-",dir=work) as tmp:
                staging=Path(tmp)
                for item in manifest["segments"]:
                    name=item["name"]
                    target=staging/name
                    await self.db.download_storage_file(self.bucket,prefix+"/"+name,target,max_bytes=item["size"])
                    if target.stat().st_size!=item["size"] or sha256_file(target)!=item["sha256"]:
                        raise ValueError("Checkpoint integrity mismatch")
                for entry in entries:
                    target=work/entry["name"]
                    # Exclusive link on the same filesystem, never overwrite.
                    os.link(staging/entry["name"],target)
                    committed.append(target)
            success=True
            logger.info("restored scene=%s segments=%s",index+1,len(entries))
            return entries
        except Exception as exc:
            logger.warning("scene checkpoint unavailable index=%s: %s",index,type(exc).__name__)
            return None
        finally:
            if not success:
                for file in committed: file.unlink(missing_ok=True)

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
