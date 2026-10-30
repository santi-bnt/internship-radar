from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "Internship Radar API"
    environment: str = "development"
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'internship_radar.db').as_posix()}"
    frontend_url: str = "http://localhost:3000"
    request_timeout_seconds: float = 15.0
    source_rate_limit_seconds: float = 0.25
    scheduler_enabled: bool = False
    search_scheduler_enabled: bool = False
    high_priority_search_interval_hours: int = 6
    general_search_interval_hours: int = 24
    verify_jobs_interval_hours: int = 24
    job_revalidation_retry_minutes: int = 30
    job_revalidation_deadline_window_hours: int = 72
    job_revalidation_batch_size: int = 100
    discovery_global_concurrency: int = 2
    discovery_per_domain_concurrency: int = 1
    discovery_source_batch_size: int = 8
    discovery_job_batch_size: int = 250
    discovery_jitter_seconds: int = 900
    discovery_group_interval_hours: int = 24
    discovery_group_hour_offsets: str = ""
    discovery_retry_base_seconds: int = 300
    discovery_retry_max_seconds: int = 21600
    expire_jobs_interval_hours: int = 24
    scheduler_hour: int = 7
    major_source_interval_hours: int = 6
    secondary_source_interval_hours: int = 12
    missing_refreshes_before_close: int = 3
    embedded_jobs_max_details: int = 20
    embedded_jobs_delay_seconds: float = 0.8
    community_source_stale_days: int = 90
    demo_feed_enabled: bool = False
    user_agent: str = "InternshipRadar/1.0 (+local educational job tracker)"
    email_enabled: bool = False
    email_recipient: str = "notifications@example.com"
    email_provider: str = "console"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_from_name: str = "Internship Radar"
    smtp_from_email: str = ""
    app_base_url: str = "http://localhost:3000"
    email_priority_alerts: bool = True
    email_daily_digest: bool = False
    email_deadline_alerts: bool = False
    email_follow_up_alerts: bool = False
    email_status_change_alerts: bool = False
    email_digest_hour: int = 8
    user_timezone: str = "America/Mexico_City"
    public_demo_mode: bool = False
    app_access_enabled: bool = False
    local_development_mode: bool = False
    internal_api_secret: str = ""
    user_identity_signing_secret: str = ""
    primary_user_id: str = ""
    authorized_user_emails: str = ""
    candidate_account_ids: str = ""
    resume_email: str = "resume@example.com"
    notification_email: str = "notifications@example.com"
    resume_generation_provider: str = "local"
    openai_api_key: str = ""
    openai_resume_model: str = "gpt-5.6"
    openai_timeout_seconds: float = 60.0
    ai_mode: str = "BALANCED"
    local_ai_base_url: str = "http://127.0.0.1:11434"
    local_ai_model: str = "qwen2.5:7b-instruct"
    local_ai_timeout_seconds: float = 20.0
    external_ai_model: str = "gpt-5.6"
    ai_max_attempts: int = 4
    # Kept in one environment setting so every resume surface has the same
    # budget. The Vercel proxy reads RESUME_GENERATION_LIMIT_PER_HOUR too.
    resume_generation_limit_per_hour: int = 30
    resume_generation_global_concurrency: int = 2
    tectonic_path: str = "tectonic"
    tectonic_timeout_seconds: int = 45
    port: int = 8000

    @property
    def authorized_email_set(self) -> frozenset[str]:
        return frozenset(
            email.strip().lower()
            for email in self.authorized_user_emails.split(",")
            if email.strip() and "@" in email
        )

    @property
    def effective_primary_user_id(self) -> str:
        return self.primary_user_id.strip() or "primary-user"

    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR.parent / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
