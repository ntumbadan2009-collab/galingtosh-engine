from __future__ import annotations
import re
from pathlib import Path
from urllib.parse import quote
import httpx

PATCHABLE_JOB_FIELDS = {"status", "progress", "output_path", "error", "warnings", "finished_at"}
ALLOWED_UPLOAD_BUCKETS = {"renders", "temp-assets"}

class SupabaseError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None, response_body: str = ""):
        self.status_code = status_code
        self.response_body = response_body
        detail = f" HTTP {status_code}" if status_code is not None else ""
        if response_body:
            detail += f" — {response_body[:2000]}"
        super().__init__(f"{message}{detail}")

class SupabaseREST:
    """Client REST minimal, limité au contrat de données Galingtosh."""
    def __init__(self, url: str, service_role_key: str, timeout: float = 30.0):
        if not url or not service_role_key:
            raise SupabaseError("Configuration Supabase absente.")
        self.base = url.rstrip("/")
        self.key = service_role_key
        self.timeout = timeout

    def _headers(self):
        return {"apikey": self.key, "Authorization": f"Bearer {self.key}"}

    async def _request(self, method: str, path: str, **kwargs):
        headers = {**self._headers(), **kwargs.pop("headers", {})}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.request(method, f"{self.base}{path}", headers=headers, **kwargs)
        if response.status_code >= 400:
            # Le corps aide au diagnostic (PostgREST renvoie code/message/details).
            # Ne jamais journaliser les en-têtes : ils contiennent la clé service_role.
            raise SupabaseError(
                "Opération Supabase impossible.",
                status_code=response.status_code,
                response_body=response.text,
            )
        return response

    async def check_auth(self) -> None:
        """Vérifie au démarrage que l'URL et la clé accèdent à l'API REST."""
        await self._request(
            "GET", "/rest/v1/render_jobs",
            params={"select": "id", "limit": "0"},
        )

    async def read_film(self, project_id: str, version: int) -> dict:
        params = {"project_id": f"eq.{project_id}", "version": f"eq.{version}", "select": "data"}
        response = await self._request("GET", "/rest/v1/films", params=params)
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
        return (await self._request("GET", "/rest/v1/media_assets", params=params)).json()

    async def claim_render_job(self, worker_id: str) -> dict | None:
        response = await self._request("POST", "/rest/v1/rpc/claim_render_job",
                                       json={"p_worker_id": worker_id})
        rows = response.json()
        return rows[0] if isinstance(rows, list) and rows else None

    async def requeue_stale_render_jobs(self) -> int:
        response = await self._request("POST", "/rest/v1/rpc/requeue_stale_render_jobs",
                                       json={"p_stale": "10 minutes", "p_max_attempts": 3})
        try:
            return int(response.json())
        except (TypeError, ValueError):
            return 0

    async def get_render_job(self, job_id: str) -> dict:
        params = {"id": f"eq.{job_id}", "select": "id,project_id,user_id,film_version,status,worker_id,progress,output_path,error,warnings,attempts"}
        rows = (await self._request("GET", "/rest/v1/render_jobs", params=params)).json()
        if not rows:
            raise SupabaseError("Tâche de rendu introuvable.")
        return rows[0]

    async def patch_render_job(self, job_id: str, fields: dict) -> None:
        if not fields or set(fields) - PATCHABLE_JOB_FIELDS:
            raise SupabaseError("Champs de mise à jour de tâche interdits.")
        await self._request("PATCH", "/rest/v1/render_jobs", params={"id": f"eq.{job_id}"},
                            json=fields, headers={**self._headers(), "Prefer": "return=minimal"})

    async def upload_file(self, bucket: str, object_path: str, source: Path,
                          content_type: str = "application/octet-stream") -> None:
        if bucket not in ALLOWED_UPLOAD_BUCKETS:
            raise SupabaseError("Bucket de destination interdit.")
        clean = object_path.replace("\\", "/")
        if clean.startswith("/") or "\x00" in clean or any(p in {"", ".", ".."} for p in clean.split("/")):
            raise SupabaseError("Chemin de destination invalide.")
        if not source.is_file() or source.stat().st_size > 50 * 1024 * 1024:
            raise SupabaseError("Fichier de rendu absent ou trop volumineux.")
        url = f"{self.base}/storage/v1/object/{bucket}/{quote(clean, safe='/')}"
        with source.open("rb") as stream:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=10)) as client:
                response = await client.post(url, headers={**self._headers(), "x-upsert": "true",
                    "Content-Type": content_type}, content=stream)
        if response.status_code >= 400:
            raise SupabaseError("Envoi du fichier rendu impossible.")

    async def download_user_upload(self, storage_path: str, user_id: str, destination: Path,
                                   max_bytes: int = 200 * 1024 * 1024) -> tuple[int, str]:
        safe_path = validate_upload_path(storage_path, user_id)
        url = f"{self.base}/storage/v1/object/user-uploads/{quote(safe_path, safe='/')}"
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
                    if length:
                        try:
                            if int(length) > max_bytes:
                                raise SupabaseError("Média privé trop volumineux.")
                        except ValueError:
                            raise SupabaseError("Taille du média privé invalide.") from None
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
    raw = str(storage_path or "").replace("\\", "/")
    if raw.startswith("/") or raw.endswith("/"):
        raise SupabaseError("Chemin de média privé invalide.")
    parts = raw.split("/")
    if not raw or len(parts) < 2 or parts[0] != str(user_id):
        raise SupabaseError("Chemin de média privé hors du dossier utilisateur.")
    if any(part in {"", ".", ".."} or "\x00" in part for part in parts):
        raise SupabaseError("Chemin de média privé invalide.")
    return raw
