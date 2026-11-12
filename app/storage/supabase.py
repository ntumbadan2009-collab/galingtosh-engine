from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

ALLOWED_JOB_PATCH_FIELDS = {"status", "progress", "output_path", "error", "warnings", "finished_at"}
VALID_STATUSES = {"queued", "running", "done", "failed", "canceled"}

class SupabaseError(RuntimeError):
    """Erreur Supabase volontairement dépourvue de corps HTTP sensible."""

class SupabaseREST:
    def __init__(self, url: str, service_role_key: str, *, client: httpx.AsyncClient | None = None):
        if not url or not service_role_key:
            raise ValueError("Configuration Supabase incomplète.")
        self.base_url = url.rstrip("/")
        self._key = service_role_key
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self):
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=8.0))
        return self

    async def __aexit__(self, *_):
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _headers(self, *, content_type: str | None = None) -> dict[str, str]:
        headers = {"apikey": self._key, "Authorization": f"Bearer {self._key}", "Accept": "application/json"}
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=8.0))
        headers = self._headers()
        headers.update(kwargs.pop("headers", {}))
        try:
            response = await self._client.request(method, f"{self.base_url}{path}", headers=headers, **kwargs)
            response.raise_for_status()
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            # Do not propagate response bodies: they may contain sensitive server details.
            raise SupabaseError(f"Échec de communication Supabase ({method} {path.split('?')[0]}).") from None
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.content

    async def claim_render_job(self, worker_id: str) -> dict[str, Any] | None:
        result = await self._request("POST", "/rest/v1/rpc/claim_render_job", json={"p_worker_id": worker_id})
        if result is None or result == []:
            return None
        if isinstance(result, list):
            return result[0] if result else None
        if isinstance(result, dict):
            return result
        raise SupabaseError("Réponse inattendue lors de la réservation d'une tâche.")

    async def requeue_stale_render_jobs(self, stale: str = "10 minutes", max_attempts: int = 3) -> int:
        result = await self._request(
            "POST", "/rest/v1/rpc/requeue_stale_render_jobs",
            json={"p_stale": stale, "p_max_attempts": max_attempts},
        )
        if isinstance(result, int):
            return result
        if isinstance(result, list) and result and isinstance(result[0], int):
            return result[0]
        raise SupabaseError("Réponse inattendue lors de la récupération des tâches bloquées.")

    async def get_render_job(self, job_id: str) -> dict[str, Any] | None:
        rows = await self._request("GET", "/rest/v1/render_jobs", params={
            "id": f"eq.{job_id}",
            "select": "id,project_id,user_id,film_version,status,worker_id,progress,output_path,error,warnings,attempts,created_at,updated_at,finished_at",
            "limit": "1",
        })
        return rows[0] if isinstance(rows, list) and rows else None

    async def get_film_data(self, project_id: str, film_version: int) -> dict[str, Any] | None:
        rows = await self._request("GET", "/rest/v1/films", params={
            "project_id": f"eq.{project_id}", "version": f"eq.{film_version}", "select": "data", "limit": "1"
        })
        if not isinstance(rows, list) or not rows:
            return None
        data = rows[0].get("data")
        return data if isinstance(data, dict) else None

    async def get_media_assets(self, project_id: str, media_ids: list[str]) -> list[dict[str, Any]]:
        if not media_ids:
            return []
        # PostgREST in.(...) filter; IDs originate from the Film JSON, not user-built query fragments.
        values = ",".join(media_ids)
        rows = await self._request("GET", "/rest/v1/media_assets", params={
            "project_id": f"eq.{project_id}", "id": f"in.({values})",
            "select": "id,project_id,kind,source,storage_path,license,provenance,analysis",
        })
        return rows if isinstance(rows, list) else []

    async def patch_render_job(self, job_id: str, changes: dict[str, Any]) -> None:
        if not changes or set(changes) - ALLOWED_JOB_PATCH_FIELDS:
            raise ValueError("Champs de mise à jour render_jobs non autorisés.")
        if "status" in changes and changes["status"] not in VALID_STATUSES:
            raise ValueError("Statut de tâche invalide.")
        if "progress" in changes and (not isinstance(changes["progress"], int) or not 0 <= changes["progress"] <= 100):
            raise ValueError("La progression doit être un entier entre 0 et 100.")
        await self._request("PATCH", "/rest/v1/render_jobs", params={"id": f"eq.{job_id}"},
                            json=changes, headers={"Prefer": "return=minimal"})

    async def upload_object(self, bucket: str, path: str, content: bytes, content_type: str) -> None:
        if bucket not in {"renders", "temp-assets"}:
            raise ValueError("Bucket de destination interdit.")
        if not path or path.startswith("/") or ".." in path.split("/"):
            raise ValueError("Chemin de stockage invalide.")
        encoded = quote(path, safe="/")
        await self._request("POST", f"/storage/v1/object/{bucket}/{encoded}", content=content,
                            headers={"Content-Type": content_type, "x-upsert": "true"})

    async def download_user_upload(self, storage_path: str) -> bytes:
        if not storage_path or storage_path.startswith("/") or ".." in storage_path.split("/"):
            raise ValueError("Chemin de média invalide.")
        encoded = quote(storage_path, safe="/")
        result = await self._request("GET", f"/storage/v1/object/user-uploads/{encoded}")
        if not isinstance(result, bytes):
            raise SupabaseError("Le téléchargement du média a retourné un format inattendu.")
        return result
