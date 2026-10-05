"""Application configuration, loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Every field below is read from an environment variable of the same
    name (case-insensitive), falling back to the .env file.

    Pydantic validates types on load, so a malformed value fails loudly
    at startup rather than mysteriously at the first database query.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Ignore env vars we don't declare rather than erroring.
        # POSTGRES_USER and friends exist for Docker, not for this app.
        extra="ignore",
    )

    # No default — the app must not start without a database.
    database_url: str

    # Defaults mean these are optional in .env.
    app_name: str = "Network Security Operations Platform"
    sql_echo: bool = False


# Single shared instance, imported everywhere else.
# Constructing Settings() reads the environment exactly once at startup.
settings = Settings()




