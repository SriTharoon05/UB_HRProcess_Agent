from functools import lru_cache
from pathlib import Path
import re
from typing import Literal

from pydantic import AliasChoices, Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.errors import ConfigurationError
from app.observability import configure_logging, log_event, stage


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False, populate_by_name=True)
    app_name: str = "TalentMatch AI"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    app_env: Literal["development", "test", "production"] = "development"
    demo_mode: bool = True
    frontend_url: str = Field(
        default="http://localhost:5173", validation_alias=AliasChoices("FRONTEND_BASE_URL", "FRONTEND_URL")
    )
    backend_url: str = Field(
        default="http://localhost:8000", validation_alias=AliasChoices("BACKEND_BASE_URL", "BACKEND_URL")
    )
    cors_origins: list[str] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
        validation_alias=AliasChoices("CORS_ALLOWED_ORIGINS", "CORS_ORIGINS"),
    )
    session_cookie_name: str = "talentmatch_session"
    session_ttl_seconds: int = Field(default=28800, ge=300, le=86400)
    redis_url: str = Field(default="redis://localhost:6379/0", repr=False)
    redis_prefix: str = "talentmatch"
    max_resume_size_mb: int = Field(default=10, ge=1, le=25)
    max_resume_uncompressed_mb: int = 40
    local_resume_dir: Path = Path(".local/resumes")
    retention_days: int = Field(default=90, ge=1)
    consent_version: str = "v1"
    public_rate_limit: int = 120
    upload_rate_limit: int = 10
    hr_login_rate_limit: int = Field(default=5, ge=1, le=120)
    hr_username: str = Field(default="", max_length=320, repr=False)
    hr_password: str = Field(default="", max_length=1024, repr=False)
    linkedin_client_id: str = ""
    linkedin_client_secret: str = Field(default="", repr=False)
    linkedin_redirect_uri: str = "http://localhost:8000/auth/linkedin/callback"
    linkedin_issuer: str = "https://www.linkedin.com/oauth"
    linkedin_discovery_url: str = "https://www.linkedin.com/oauth/.well-known/openid-configuration"
    entra_tenant_id: str = Field(default="", validation_alias=AliasChoices("HR_ENTRA_TENANT_ID", "ENTRA_TENANT_ID"))
    entra_client_id: str = Field(default="", validation_alias=AliasChoices("HR_ENTRA_CLIENT_ID", "ENTRA_CLIENT_ID"))
    entra_client_secret: str = Field(
        default="", repr=False, validation_alias=AliasChoices("HR_ENTRA_CLIENT_SECRET", "ENTRA_CLIENT_SECRET")
    )
    entra_redirect_uri: str = Field(
        default="http://localhost:8000/auth/hr/callback",
        validation_alias=AliasChoices("HR_ENTRA_REDIRECT_URI", "ENTRA_REDIRECT_URI"),
    )
    entra_hr_role: str = "TalentMatch.HR"
    hr_allowed_roles: list[str] = ["HRRecruiter", "HRAdministrator", "TalentMatch.HR"]
    d365_contract_mode: Literal["sqlite", "legacy"] = "sqlite"
    sqlite_database_path: Path = Path(".local/talentmatch.sqlite3")
    metadata_backend: Literal["sqlite", "postgres"] = "sqlite"
    database_url: str = Field(default="", repr=False, max_length=4096)
    database_sslmode: Literal["verify-full", "require", "disable"] = "verify-full"
    database_sslrootcert: Path | None = None
    database_connect_timeout: int = Field(default=10, ge=1, le=60)
    d365_enabled: bool = False
    d365_base_url: str = "https://org1a43c536.operations.dynamics.com"
    d365_tenant_id: str = ""
    d365_client_id: str = ""
    d365_client_secret: str = Field(default="", repr=False)
    d365_company: str = "DAT"
    d365_parameter_name: str = "_request"
    d365_requirement_path: str = "/api/services/UBHRPortalServiceGroup/UBHRPortalService/getOpenRequirements"
    d365_submit_application_path: str = (
        "/api/services/UBHRPortalServiceGroup/UBHRPortalService/submitApplication"
    )
    d365_save_evaluation_path: str = Field(
        default="/api/services/UBHRPortalServiceGroup/UBHRPortalService/saveCandidateEvaluation",
        validation_alias=AliasChoices("D365_SAVE_EVALUATION_PATH", "D365_SAVE_CANDIDATE_EVALUATION_PATH"),
    )
    d365_top_candidates_path: str = ""
    d365_my_applications_path: str = ""
    d365_application_path: str = ""
    d365_http_timeout: float = 30
    d365_request_wrappers: dict[str, str] = {"get_open_requirements": ""}
    d365_request_field_maps: dict[str, dict[str, str]] = {}
    d365_response_field_maps: dict[str, dict[str, str]] = {}
    azure_openai_endpoint: str = "https://voiceagentdemo-resource.cognitiveservices.azure.com/"
    azure_openai_api_key: str = Field(default="", repr=False)
    azure_openai_deployment: str = "gpt-4.1-mini"
    azure_openai_api_version: str = "2025-03-01-preview"
    azure_openai_prompt_version: str = "v1"
    azure_openai_max_resume_chars: int = 100000
    azure_openai_validation_attempts: int = Field(default=3, ge=1, le=3)
    azure_storage_connection_string: str = Field(default="", repr=False)
    azure_storage_container: str = "resumes"
    evaluation_max_attempts: int = Field(default=5, ge=1, le=10)

    @field_validator("database_sslrootcert", mode="before")
    @classmethod
    def optional_database_certificate(cls, value):
        # A copied .env template intentionally leaves this optional setting
        # blank. Path("") would become '.', which libpq cannot use as a CA file.
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def resolve_sqlite_evaluation_endpoint(self):
        # Older .env files contain an empty save path. An explicit empty string
        # overrides the Pydantic default, so restore the three-operation F&O
        # contract in SQLite mode without changing optional legacy operations.
        self.d365_save_evaluation_path = self.d365_save_evaluation_path.strip()
        if self.d365_contract_mode == "sqlite" and not self.d365_save_evaluation_path:
            service = re.fullmatch(
                r"(/api/services/[A-Za-z0-9_]+/[A-Za-z0-9_]+)/submitApplication",
                self.d365_submit_application_path.strip(), flags=re.IGNORECASE,
            )
            if service:
                self.d365_save_evaluation_path = service.group(1) + "/saveCandidateEvaluation"
            else:
                self.d365_save_evaluation_path = type(self).model_fields["d365_save_evaluation_path"].default
            log_event("configuration.d365_evaluation_endpoint", "defaulted",
                      field="d365_save_evaluation_path", reason="blank_setting",
                      source="application_service" if service else "sqlite_contract_default")
        return self

    @model_validator(mode="after")
    def secure_production(self):
        if "*" in self.cors_origins:
            raise ValueError("CORS must use explicit allowed origins")
        if self.app_env == "production":
            if self.demo_mode:
                raise ValueError("DEMO_MODE must be false in production")
            if not self.frontend_url.startswith("https://") or not self.backend_url.startswith("https://"):
                raise ValueError("Production frontend and backend URLs must use HTTPS")
            if any(not origin.startswith("https://") for origin in self.cors_origins):
                raise ValueError("Production CORS origins must use HTTPS")
        return self


@lru_cache
def get_settings() -> Settings:
    # Pydantic root-validation errors can include the entire environment input
    # dictionary. Emit field names only, then raise a value-free startup error.
    configure_logging()
    with stage("configuration.load"):
        try:
            settings = Settings()
        except ValidationError as exc:
            for failure in exc.errors(include_url=False, include_context=False, include_input=False):
                field = failure["loc"][0] if failure["loc"] else "production_configuration"
                log_event("configuration.validate", "rejected", field=str(field), reason="invalid_setting")
            raise ConfigurationError("Application settings are invalid. Check configuration.validate in the terminal.") from None
        configure_logging(settings.log_level)
        return settings
