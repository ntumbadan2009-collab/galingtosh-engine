from __future__ import annotations
import re
from pathlib import Path
from urllib.parse import quote
import httpx

class SupabaseError(RuntimeError):
    pass

class SupabaseREST:
    """Client REST minimal. Toutes les écritures restent hors de ce module sauf Storage."""
    def __init__(self, url: str, service_role_key: str, timeout: float = 30.0):
        if not url or not service_role_key:
            raise SupabaseError("Configuration Supabase absente.")
        self.base = url.rstrip("/")
        self.key = service_role_key
        self.timeout = timeout

    def _headers(self):
        return {"apikey": self.key, "Authorization": f"Bearer {self.key}"}

    async def read_film(self, project_id: str, version: int) -> dict:
        params = {"project_id": f"eq.{project_id}", "version": f"eq.{version}", "select": "data"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base}/rest/v1/films", params=params, headers=self._headers())
        if response.status_code >= 400:
            raise SupabaseError("Lecture du Film JSON impossible.")
        rows = response.json()
        if not rows or not isinstance(rows[0].get("data"), dict):
            raise SupabaseError("Version du Film JSON introuvable.")
        return rows[0]["data"]

    async def read_media_assets(self, project_id: str, media_ids: list[str]) -> list[dict]:
        ids = sorted({str(x) for x in media_ids if x})
        if not ids:
            return []
        if any(not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", item) for item in ids):
            raise SupabaseError("Identifiant de média invalide.")
        params = {"project_id": f"eq.{project_id}", "id": f"in.({','.join(ids)})",
                  "select": "id,project_id,kind,source,storage_path,license,provenance,analysis"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base}/rest/v1/media_assets", params=params, headers=self._headers())
        if response.status_code >= 400:
            raise SupabaseError("Lecture des références média impossible.")
        return response.json()

    async def download_user_upload(self, storage_path: str, user_id: str, destination: Path,
                                   max_bytes: int = 200 * 1024 * 1024) -> tuple[int, str]:
        safe_path = validate_upload_path(storage_path, user_id)
        encoded = quote(safe_path, safe="/")
        url = f"{self.base}/storage/v1/object/user-uploads/{encoded}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        content_type = ""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10)) as client:
                async with client.stream("GET", url, headers=self._headers()) as response:
                    if response.status_code >= 400:
                        raise SupabaseError("Téléchargement du média privé impossible.")
                    content_type = response.headers.get("content-type", "").split(";")[0].lower()
                    length = response.headers.get("content-length")
                    if length and int(length) > max_bytes:
                        raise SupabaseError("Média privé trop volumineux.")
                    with destination.open("wb") as output:
                        async for chunk in response.aiter_bytes(64 * 1024):
                            total += len(chunk)
                            if total > max_bytes:
                                raise SupabaseError("Média privé trop volumineux.")
                            output.write(chunk)
            if total == 0:
                raise SupabaseError("Média privé vide.")
            return total, content_type
        except Exception:
            destination.unlink(missing_ok=True)
            raise

def validate_upload_path(storage_path: str, user_id: str) -> str:
    path = str(storage_path or "").replace("\\", "/").strip("/")
    parts = path.split("/")
    if not path or len(parts) < 2 or parts[0] != str(user_id):
        raise SupabaseError("Chemin de média privé hors du dossier utilisateur.")
    if any(part in {"", ".", ".."} or "\x00" in part for part in parts):
        raise SupabaseError("Chemin de média privé invalide.")
    return path
