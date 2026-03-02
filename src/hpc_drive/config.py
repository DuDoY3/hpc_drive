import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./drive.db"

    AUTH_SERVICE_ME_URL: str = "http://localhost:8082/api/v1/me"  # Fixed: 8082 not 8082
    LEARNING_SERVICE_URL: str = os.getenv(
        "LEARNING_SERVICE_URL", "http://localhost:8000"
    )

    # File storage directory
    UPLOAD_DIR: str = "uploads"

    class Config:
        env_file: str = ".env"

    UPLOADS_DIR: Path = Path(__file__).resolve().parent / "uploads"


settings = Settings()