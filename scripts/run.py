#!/usr/bin/env python3
"""Chạy LENN Core: python3 scripts/run.py [--config config.json]"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn

from lenn_core.api.app import create_app
from lenn_core.config import LennCoreConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="LENN Core (Phase 0)")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    config = LennCoreConfig.load(Path(args.config))
    if args.host:
        config.http_host = args.host
    if args.port:
        config.http_port = args.port

    app = create_app(config)
    uvicorn.run(app, host=config.http_host, port=config.http_port, log_level="info")


if __name__ == "__main__":
    main()
