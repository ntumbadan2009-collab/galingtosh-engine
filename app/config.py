from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    app_name: str = "Galingtosh Engine"
    environment: str = "production"
    supabase_url: str = "https://lmlwekcytivszlszmfvy.supabase.co"
    supabase_service_role_key: str = ""
    engine_shared_secret: str = ""
    worker_id: str = "galingtosh-engine"
    poll_interval_seconds: int = Field(default=8, ge=2, le=120)
    max_render_seconds: int = Field(default=600, ge=30)
    max_output_mb: int = Field(default=45, ge=1, le=49)
    temp_dir: str = "/tmp/galingtosh"

@lru_cache
def get_settings() -> Settings:
    return Settings()
