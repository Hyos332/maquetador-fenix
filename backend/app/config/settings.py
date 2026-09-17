from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


class Settings(BaseModel):
    app_name: str = "Maquetador MLS"
    workspaces_dir: Path = Field(default=Path("../workspaces"))
    deliveries_dir: Path = Field(default=Path("../deliveries"))
    maquetador_url: str = "http://172.22.104.76:8087/"
    playwright_headless: bool = False
    dry_run: bool = True
    max_zip_size_mb: int = 100

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_name=os.getenv("MLS_APP_NAME", cls.model_fields["app_name"].default),
            workspaces_dir=Path(
                os.getenv(
                    "MLS_WORKSPACES_DIR",
                    str(cls.model_fields["workspaces_dir"].default),
                )
            ),
            deliveries_dir=Path(
                os.getenv(
                    "MLS_DELIVERIES_DIR",
                    str(cls.model_fields["deliveries_dir"].default),
                )
            ),
            maquetador_url=os.getenv(
                "MLS_MAQUETADOR_URL",
                cls.model_fields["maquetador_url"].default,
            ),
            playwright_headless=_env_bool(
                "MLS_PLAYWRIGHT_HEADLESS",
                cls.model_fields["playwright_headless"].default,
            ),
            dry_run=_env_bool("MLS_DRY_RUN", cls.model_fields["dry_run"].default),
            max_zip_size_mb=int(
                os.getenv(
                    "MLS_MAX_ZIP_SIZE_MB",
                    str(cls.model_fields["max_zip_size_mb"].default),
                )
            ),
        )


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


settings = Settings.from_env()
