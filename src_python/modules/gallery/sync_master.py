from __future__ import annotations

import os
from pathlib import Path


def canonicalize_path(path: str) -> str:
    raw = (path or "").strip()
    if not raw:
        return ""
    try:
        normalized = str(Path(raw).resolve())
    except Exception:
        normalized = str(Path(raw))
    normalized = normalized.rstrip("\\/")
    return normalized.lower() if os.name == "nt" else normalized


def list_master_roots(master_path: str) -> list[Path]:
    if not master_path or not master_path.strip():
        raise ValueError("La ruta maestra no puede estar vacía.")
    master_dir = Path(master_path.strip())
    if not master_dir.exists():
        raise ValueError(f"La ruta maestra no existe: {master_dir}")
    if not master_dir.is_dir():
        raise ValueError(f"La ruta maestra no es una carpeta: {master_dir}")
    return sorted(
        [
            p
            for p in master_dir.iterdir()
            if p.is_dir() and p.name.casefold() != "thumb"
        ],
        key=lambda p: p.name.lower(),
    )
