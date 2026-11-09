import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from src_python.modules.gallery.router import (
    _organizer_child_path,
    _organizer_prefix,
    _organizer_relative_parts,
    _organizer_tree,
    _validate_organizer_folder_name,
    OrganizerFolderRenameRequest,
    rename_organizer_folder,
)


def test_organizer_tree_ignores_thumb_and_counts_nested_images(tmp_path: Path):
    alice = tmp_path / "Personajes" / "Alice"
    (alice / "thumb").mkdir(parents=True)
    (alice / "alice_01.png").write_bytes(b"image")
    (alice / "thumb" / "alice_01.jpg").write_bytes(b"thumb")
    (tmp_path / "Personajes" / "Prototipos" / "Fase 1").mkdir(parents=True)

    tree, total = _organizer_tree(tmp_path)

    assert total == 1
    assert [node["name"] for node in tree] == ["Personajes"]
    assert tree[0]["total_image_count"] == 1
    assert [node["name"] for node in tree[0]["children"]] == ["Prototipos", "Alice"]
    alice_node = next(node for node in tree[0]["children"] if node["name"] == "Alice")
    assert alice_node["image_count"] == 1
    assert alice_node["has_thumb"] is True
    assert all(child["name"] != "thumb" for child in alice_node["children"])


@pytest.mark.parametrize("value", ["../fuera", "Personajes/../fuera", "/absoluta", "C:/absoluta", "thumb"])
def test_organizer_rejects_unsafe_or_reserved_paths(tmp_path: Path, value: str):
    with pytest.raises(ValueError):
        _organizer_relative_parts(value, allow_empty=False)
    with pytest.raises(ValueError):
        _organizer_child_path(tmp_path, value, allow_empty=False)


def test_organizer_prefix_is_stable_for_correlative_names():
    assert _organizer_prefix("Boss") == "boss"
    assert _organizer_prefix("Prototipo Final") == "prototipo_final"
    assert _organizer_prefix("2026-04-01") == "2026-04-01"


def test_organizer_folder_name_validation_for_rename():
    assert _validate_organizer_folder_name("  Boss Final  ") == "Boss Final"
    for invalid in ("thumb", "..", "Boss/Final", "Boss?", "Boss."):
        with pytest.raises(ValueError):
            _validate_organizer_folder_name(invalid)


def test_rename_organizer_folder_updates_files_thumbs_and_persisted_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "Boss"
    thumb = source / "thumb"
    child = source / "Prototipos"
    thumb.mkdir(parents=True)
    child.mkdir()
    (source / "first.png").write_bytes(b"one")
    (source / "second.webp").write_bytes(b"two")
    (thumb / "first.jpg").write_bytes(b"thumb-one")
    (thumb / "second.jpg").write_bytes(b"thumb-two")
    (child / "nested.png").write_bytes(b"nested")

    direct_one = SimpleNamespace(
        folder_id="ordered",
        path="Boss/first.png",
        thumb_path="Boss/thumb/first.jpg",
    )
    direct_two = SimpleNamespace(
        folder_id="ordered",
        path="Boss/second.webp",
        thumb_path="Boss/thumb/second.jpg",
    )
    nested = SimpleNamespace(
        folder_id="ordered",
        path="Boss/Prototipos/nested.png",
        thumb_path=None,
    )
    root_node = SimpleNamespace(rel_path="Boss", name="Boss")
    child_node = SimpleNamespace(rel_path="Boss/Prototipos", name="Prototipos")

    class FakeScalars:
        def __init__(self, values):
            self.values = values

        def all(self):
            return self.values

    class FakeResult:
        def __init__(self, values):
            self.values = values

        def scalars(self):
            return FakeScalars(self.values)

    class FakeDb:
        def __init__(self):
            self.calls = 0
            self.committed = False
            self.rolled_back = False

        async def execute(self, _statement):
            self.calls += 1
            if self.calls == 1:
                return FakeResult([direct_one, direct_two, nested])
            return FakeResult([root_node, child_node])

        async def commit(self):
            self.committed = True

        async def rollback(self):
            self.rolled_back = True

    async def fake_root(_db, *, create=False):
        return tmp_path

    async def no_configuration_error(_db, _root):
        return None

    monkeypatch.setattr(
        "src_python.modules.gallery.router._get_organizer_root",
        fake_root,
    )
    monkeypatch.setattr(
        "src_python.modules.gallery.router._organizer_configuration_error",
        no_configuration_error,
    )

    db = FakeDb()
    response = asyncio.run(
        rename_organizer_folder(
            OrganizerFolderRenameRequest(path="Boss", new_name="Final Boss"),
            db,
        )
    )

    target = tmp_path / "Final Boss"
    assert db.committed is True
    assert db.rolled_back is False
    assert source.exists() is False
    assert (target / "final_boss_01.png").read_bytes() == b"one"
    assert (target / "final_boss_02.webp").read_bytes() == b"two"
    assert (target / "thumb" / "final_boss_01.jpg").read_bytes() == b"thumb-one"
    assert (target / "thumb" / "final_boss_02.jpg").read_bytes() == b"thumb-two"
    assert (target / "Prototipos" / "nested.png").read_bytes() == b"nested"
    assert direct_one.path == "Final Boss/final_boss_01.png"
    assert direct_one.thumb_path == "Final Boss/thumb/final_boss_01.jpg"
    assert direct_two.path == "Final Boss/final_boss_02.webp"
    assert nested.path == "Final Boss/Prototipos/nested.png"
    assert root_node.rel_path == "Final Boss"
    assert root_node.name == "Final Boss"
    assert child_node.rel_path == "Final Boss/Prototipos"
    assert child_node.name == "Prototipos"
    assert response["renamed_image_count"] == 2
