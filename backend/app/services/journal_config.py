from __future__ import annotations

from pathlib import Path

import yaml

from app.models.journal import JournalConfig


class JournalConfigService:
    def __init__(self, journals_dir: Path | None = None) -> None:
        self.journals_dir = journals_dir or Path(__file__).resolve().parents[1] / "config" / "journals"

    def load(self, key: str) -> JournalConfig:
        path = self.journals_dir / f"{key}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Journal config not found: {key}")

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return JournalConfig.model_validate({**data, "source_path": path})

    def list_available(self) -> list[JournalConfig]:
        return [self.load(path.stem) for path in sorted(self.journals_dir.glob("*.yaml"))]
