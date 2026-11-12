from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from app.media.resolver import download_public_media
from app.storage.supabase import SupabaseREST, SupabaseError

MAX_MEDIA_BYTES = 200 * 1024 * 1024
ALLOWED_MIME = {
 "image": {"image/jpeg","image/png","image/webp","image/gif","image/bmp","image/svg+xml"},
 "video": {"video/mp4","video/quicktime","video/webm","video/x-matroska"},
 "audio": {"audio/mpeg","audio/mp4","audio/wav","audio/x-wav","audio/ogg","audio/aac","audio/flac"},
 "svg": {"image/svg+xml"}, "chart": {"application/json"},
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

def _credit(media: dict) -> dict:
    p = media.get("provenance") or {}
    return {"media_id": media.get("id"), "author": p.get("author") or "Auteur non renseigné",
      "source": p.get("source") or p.get("title") or "Source non renseignée",
      "license": p.get("license") or media.get("license") or "Licence non renseignée",
      "license_url": p.get("license_url"), "url": p.get("url"),
      "attribution": p.get("attribution"), "restrictions": p.get("restrictions") or []}

def _validate_mime(kind: str, mime: str) -> None:
    if not mime or mime == "application/octet-stream":
        raise SupabaseError("Type MIME du média non vérifiable.")
    if mime not in ALLOWED_MIME.get(kind, set()):
        raise SupabaseError("Type MIME incompatible avec le média déclaré.")

async def resolve_film_media(film: dict[str, Any], project_id: str, user_id: str,
                             db: SupabaseREST, workdir: Path) -> tuple[dict[str, Path], list[str], list[dict]]:
    rows = await db.read_media_assets(project_id, _media_ids(film))
    by_id = {str(row.get("id")): row for row in rows}
    files, warnings, credits = {}, [], []
    for index, item in enumerate(film.get("media", [])):
        if not isinstance(item, dict) or not item.get("id"):
            continue
        mid = str(item["id"]); row = by_id.get(mid)
        if not row:
            warnings.append(f"Média {mid} absent de media_assets : ignoré."); continue
        kind = str(row.get("kind") or "").lower()
        if kind == "model3d":
            warnings.append(f"Média 3D {mid} non pris en charge."); continue
        if kind not in ALLOWED_MIME:
            warnings.append(f"Type de média {mid} non pris en charge."); continue
        source = str(row.get("source") or "")
        target = workdir / f"asset_{index:04d}"
        try:
            if source == "upload":
                _, mime = await db.download_user_upload(str(row.get("storage_path") or ""), user_id, target, MAX_MEDIA_BYTES)
            elif source == "search":
                provenance = row.get("provenance") or {}
                url = provenance.get("download_url") or provenance.get("preview_url")
                if not url:
                    warnings.append(f"Média recherché {mid} sans URL de téléchargement."); continue
                _, mime = await download_public_media(str(url), target, MAX_MEDIA_BYTES)
                if not mime or mime == "application/octet-stream":
                    warnings.append(f"Média {mid} : type MIME non vérifiable, ignoré."); target.unlink(missing_ok=True); continue
            else:
                warnings.append(f"Source « {source} » du média {mid} non prise en charge."); continue
            _validate_mime(kind, mime)
            suffix = EXTENSIONS[mime]
            final = target.with_suffix(suffix); target.replace(final); files[mid] = final
            if source == "search": credits.append(_credit(row))
        except Exception:
            target.unlink(missing_ok=True)
            warnings.append(f"Média {mid} indisponible ou non conforme : ignoré.")
    return files, list(dict.fromkeys(warnings)), credits

def write_credits(path: Path, credits: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(credits, ensure_ascii=False, indent=2), encoding="utf-8")
