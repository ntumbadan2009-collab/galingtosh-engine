from __future__ import annotations
import json
import mimetypes
from pathlib import Path
from typing import Any

from app.media.resolver import download_public_media
from app.storage.supabase import SupabaseREST, SupabaseError

MAX_MEDIA_BYTES = 200 * 1024 * 1024
ALLOWED_MIME = {
 "image": {"image/jpeg","image/png","image/webp","image/gif","image/bmp","image/svg+xml"},
 "video": {"video/mp4","video/quicktime","video/webm","video/x-matroska"},
 "audio": {"audio/mpeg","audio/mp4","audio/wav","audio/x-wav","audio/ogg","audio/aac","audio/flac"},
 "svg": {"image/svg+xml"},
 "chart": {"application/json"},
}
EXTENSIONS = {
 "image/jpeg":".jpg","image/png":".png","image/webp":".webp","image/gif":".gif",
 "image/bmp":".bmp","image/svg+xml":".svg","video/mp4":".mp4","video/quicktime":".mov",
 "video/webm":".webm","video/x-matroska":".mkv","audio/mpeg":".mp3","audio/mp4":".m4a",
 "audio/wav":".wav","audio/x-wav":".wav","audio/ogg":".ogg","audio/aac":".aac",
 "audio/flac":".flac","application/json":".json",
}

def _media_ids(film: dict[str, Any]) -> list[str]:
    return [str(m["id"]) for m in film.get("media", []) if isinstance(m,dict) and m.get("id")]

def _expected_kind(media: dict) -> str:
    kind = str(media.get("kind") or "").lower()
    return kind if kind in ALLOWED_MIME else ""

def _validate_mime(kind: str, content_type: str) -> None:
    if not content_type or content_type == "application/octet-stream":
        return
    if content_type not in ALLOWED_MIME.get(kind, set()):
        raise SupabaseError("Le type de contenu du média ne correspond pas à son type déclaré.")

def _credit(media: dict) -> dict:
    p = media.get("provenance") or {}
    return {
      "media_id": media.get("id"),
      "author": p.get("author") or "Auteur non renseigné",
      "source": p.get("source") or p.get("title") or "Source non renseignée",
      "license": p.get("license") or media.get("license") or "Licence non renseignée",
      "license_url": p.get("license_url"),
      "url": p.get("url"),
      "attribution": p.get("attribution"),
      "restrictions": p.get("restrictions") or [],
    }

async def resolve_film_media(
    film: dict[str, Any], project_id: str, user_id: str, db: SupabaseREST, workdir: Path,
) -> tuple[dict[str, Path], list[str], list[dict]]:
    """Matérialise localement les médias référencés. La table media_assets reste en lecture seule."""
    rows = await db.read_media_assets(project_id, _media_ids(film))
    by_id = {str(row.get("id")): row for row in rows}
    files: dict[str, Path] = {}
    warnings: list[str] = []
    credits: list[dict] = []
    for index, film_media in enumerate(film.get("media", [])):
        if not isinstance(film_media, dict) or not film_media.get("id"):
            continue
        media_id = str(film_media["id"])
        row = by_id.get(media_id)
        if not row:
            warnings.append(f"Média {media_id} absent de media_assets : ignoré.")
            continue
        kind = _expected_kind(row)
        if kind == "model3d":
            warnings.append(f"Média 3D {media_id} non pris en charge.")
            continue
        if kind not in ALLOWED_MIME:
            warnings.append(f"Type de média {media_id} non pris en charge.")
            continue
        source = str(row.get("source") or "")
        destination = workdir / f"asset_{index:04d}"
        try:
            if source == "upload":
                count, mime = await db.download_user_upload(
                    str(row.get("storage_path") or ""), user_id, destination, MAX_MEDIA_BYTES)
            elif source == "search":
                provenance = row.get("provenance") or {}
                remote_url = provenance.get("download_url") or provenance.get("preview_url")
                if not remote_url:
                    warnings.append(f"Média recherché {media_id} sans URL de téléchargement.")
                    continue
                count, mime = await download_public_media(str(remote_url), destination, MAX_MEDIA_BYTES)
                if not mime or mime == "application/octet-stream":
                    warnings.append(f"Média {media_id} : type MIME non vérifiable, fichier conservé sous réserve.")
            else:
                warnings.append(f"Source « {source} » du média {media_id} non prise en charge.")
                continue
            _validate_mime(kind, mime)
            ext = EXTENSIONS.get(mime) or Path(str(row.get("storage_path") or "")).suffix.lower()
            if not ext:
                ext = {"image":".img","video":".video","audio":".audio","svg":".svg","chart":".json"}.get(kind,".bin")
            final_path = destination.with_suffix(ext)
            destination.replace(final_path)
            files[media_id] = final_path
            if source == "search":
                credits.append(_credit(row))
        except Exception as exc:
            destination.unlink(missing_ok=True)
            warnings.append(f"Média {media_id} indisponible : {str(exc)[:160]}")
    return files, list(dict.fromkeys(warnings)), credits

def write_credits(path: Path, credits: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(credits, ensure_ascii=False, indent=2), encoding="utf-8")
