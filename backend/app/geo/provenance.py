"""Provenance: every derived/downloaded artifact is hashed and recorded with its source, licence and time."""
from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import DataSourceRow


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def record_artifact(manifest_path: Path, name: str, path: Path, source_url: str, licence: str,
                    extra: dict | None = None, base_dir: Path | None = None) -> dict:
    """Add/replace one entry in manifest.json. Paths are stored relative so the manifest is portable."""
    path = Path(path)
    entry = {
        "name": name,
        "path": str(path.relative_to(base_dir)).replace("\\", "/") if base_dir else path.name,
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "source_url": source_url,
        "licence": licence,
        "python": platform.python_version(),
        "extra": extra or {},
    }
    manifest = {"artifacts": {}}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.setdefault("artifacts", {})[name] = entry
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return entry


def mark_source_verified(session: Session, key: str) -> bool:
    """Flip a register row to VERIFIED — only call after code has really fetched and validated that source."""
    row = session.scalars(select(DataSourceRow).where(DataSourceRow.key == key)).first()
    if row is None:
        return False
    row.verification = "verified"
    row.last_checked = datetime.now(timezone.utc)
    session.commit()
    return True
