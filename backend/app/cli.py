from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config.settings import Settings
from app.pipeline.article_pipeline import ArticlePipeline


def main() -> None:
    parser = argparse.ArgumentParser(prog="mls-maquetador")
    subparsers = parser.add_subparsers(dest="command", required=True)

    maquetar = subparsers.add_parser("maquetar", help="Analiza y maqueta un ZIP de articulo.")
    maquetar.add_argument("source_zip", type=Path)
    maquetar.add_argument("--workspaces-dir", type=Path, default=Path("../workspaces"))
    maquetar.add_argument("--deliveries-dir", type=Path, default=Path("../deliveries"))

    args = parser.parse_args()
    if args.command == "maquetar":
        settings = Settings.from_env().model_copy(
            update={
                "workspaces_dir": args.workspaces_dir,
                "deliveries_dir": args.deliveries_dir,
                "dry_run": True,
            }
        )
        result = ArticlePipeline(settings).run(args.source_zip)
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
