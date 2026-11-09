from pathlib import Path

import pytest

from src_python.modules.gallery.sync_master import canonicalize_path, list_master_roots


def test_canonicalize_path_returns_empty_for_blank() -> None:
    assert canonicalize_path("   ") == ""


def test_list_master_roots_orders_by_name(tmp_path: Path) -> None:
    (tmp_path / "Beta").mkdir()
    (tmp_path / "alice").mkdir()
    (tmp_path / "An").mkdir()
    (tmp_path / "readme.txt").write_text("x", encoding="utf-8")

    roots = list_master_roots(str(tmp_path))
    assert [p.name for p in roots] == ["alice", "An", "Beta"]


def test_list_master_roots_excludes_thumbnail_folder(tmp_path: Path) -> None:
    (tmp_path / "Personajes").mkdir()
    (tmp_path / "thumb").mkdir()
    (tmp_path / "THUMB").mkdir(exist_ok=True)

    roots = list_master_roots(str(tmp_path))

    assert [p.name for p in roots] == ["Personajes"]


def test_list_master_roots_requires_existing_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        list_master_roots(str(tmp_path / "missing"))
