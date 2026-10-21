"""Command-line helpers: `python -m app.cli init-db`."""
import argparse
import sys

from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.db import get_engine, run_migrations, seed_data_sources


def init_db() -> None:
    settings = get_settings()
    run_migrations(settings.database_url)
    with sessionmaker(bind=get_engine(settings.database_url))() as session:
        added = seed_data_sources(session)
    print(f"Database ready ({settings.database_url.split('///')[0]}). Seeded {added} new data source rows.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="floodsense")
    parser.add_argument("command", choices=["init-db"])
    args = parser.parse_args(argv)
    if args.command == "init-db":
        init_db()
    return 0


if __name__ == "__main__":
    sys.exit(main())
