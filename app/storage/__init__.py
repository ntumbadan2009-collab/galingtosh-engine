"""Accès aux services de stockage autorisés par le contrat Galingtosh."""

from app.storage.supabase import SupabaseREST, SupabaseError

__all__ = ["SupabaseREST", "SupabaseError"]
