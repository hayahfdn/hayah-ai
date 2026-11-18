"""Application settings, read from environment variables (see .env.example).

Secrets (database password, JWT secret, Google and Meta credentials,
Anthropic key) are only ever read from the environment or from files under
SECRETS_DIR. Nothing here is sent to the frontend.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="HAYAH_", extra="ignore")

    env: str = "development"  # development | test | production
    database_url: str = "postgresql+psycopg://hayah:hayah@localhost:5432/hayah"

    # Auth
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 12
    login_rate_limit_per_minute: int = 10
    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    # First super admin (created by `python -m app.cli create-admin` or seed)
    bootstrap_admin_email: str = "admin@hayah.local"
    bootstrap_admin_password: str = "ChangeMe!2026"

    # Integrations: "mock" runs fully offline, "google" / "meta" / "anthropic" use real APIs.
    sheets_backend: str = "mock"
    drive_backend: str = "mock"
    whatsapp_backend: str = "mock"
    ai_backend: str = "rules"  # rules (no AI, free) | anthropic

    secrets_dir: str = "./secrets"
    mock_data_dir: str = "./data"
    google_credentials_file: str = "google-oauth-token.json"  # inside secrets_dir
    google_service_account_file: str = ""  # optional alternative, inside secrets_dir
    sheets_spreadsheet_id: str = ""
    sheets_spreadsheet_title: str = "HAYAH – MASTER OPERATIONS DATABASE"
    drive_root_folder_name: str = "HAYAH PROJECTS"
    drive_root_folder_id: str = ""

    # WhatsApp Cloud API (official). Only the intake number, never the main business number.
    whatsapp_verify_token: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_graph_version: str = "v21.0"

    # Anthropic (production AI). Off until approved.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    # USD per million tokens, used for the cost guard (update if Anthropic changes prices).
    anthropic_input_usd_per_mtok: float = 4.0
    anthropic_output_usd_per_mtok: float = 20.0
    ai_monthly_budget_usd: float = 20.0
    # Hard ceiling on AI spend per month, whatever is typed in Settings (Hayah, 18 Nov 2026).
    ai_monthly_budget_max_usd: float = 20.0
    ai_min_confidence: float = 0.90

    # Media
    max_upload_mb: int = 500

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
