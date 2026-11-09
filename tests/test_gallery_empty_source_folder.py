from pathlib import Path

import pytest

from src_python.modules.gallery.router import (
    _collapse_organizer_move_sources,
    _delete_empty_source_directory,
    _delete_image_thumbnails,
    _next_available_trash_path,
    _validate_thumbnail_only_source_folder,
)


def test_delete_empty_source_directory(tmp_path: Path):
    target = tmp_path / "empty"
    target.mkdir()

    had_thumb = _delete_empty_source_directory(target)

    assert had_thumb is False
    assert not target.exists()


def test_delete_empty_source_directory_with_empty_thumb(tmp_path: Path):
    target = tmp_path / "empty-with-thumb"
    target.mkdir()
    (target / "thumb").mkdir()

    had_thumb = _delete_empty_source_directory(target)

    assert had_thumb is True
    assert not target.exists()


def test_delete_empty_source_directory_removes_empty_subtree(tmp_path: Path):
    target = tmp_path / "fera"
    (target / "Alice" / "thumb").mkdir(parents=True)
    (target / "Boss" / "Variantes" / "thumb").mkdir(parents=True)
    (target / "Setzu").mkdir(parents=True)

    had_thumb = _delete_empty_source_directory(target)

    assert had_thumb is True
    assert not target.exists()


@pytest.mark.parametrize("relative_file", ["image.png", "thumb/image.jpg"])
def test_delete_empty_source_directory_rejects_content(tmp_path: Path, relative_file: str):
    target = tmp_path / "not-empty"
    target.mkdir()
    file_path = target / relative_file
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"content")

    with pytest.raises(ValueError):
        _delete_empty_source_directory(target)

    assert target.exists()
    assert file_path.exists()


def test_validate_thumbnail_only_source_folder_allows_residual_thumbnails(tmp_path: Path):
    target = tmp_path / "fera"
    first_thumb = target / "thumb" / "fera.jpg"
    nested_thumb = target / "Alice" / "thumb" / "alice.jpg"
    first_thumb.parent.mkdir(parents=True)
    nested_thumb.parent.mkdir(parents=True)
    first_thumb.write_bytes(b"thumb")
    nested_thumb.write_bytes(b"nested-thumb")

    assert _validate_thumbnail_only_source_folder(target) == 2


def test_validate_thumbnail_only_source_folder_rejects_original_images(tmp_path: Path):
    target = tmp_path / "fera"
    original = target / "Alice" / "alice.png"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"image")

    with pytest.raises(ValueError, match="archivos originales"):
        _validate_thumbnail_only_source_folder(target)


def test_next_available_trash_path_uses_parenthesized_counter_for_disk_collision(tmp_path: Path):
    (tmp_path / "alice.png").write_bytes(b"first")
    (tmp_path / "alice (1).png").write_bytes(b"second")

    result = _next_available_trash_path(tmp_path, "alice.png")

    assert result.name == "alice (2).png"


def test_next_available_trash_path_also_reserves_database_names(tmp_path: Path):
    result = _next_available_trash_path(tmp_path, "boss.png", {"boss.png", "boss (1).png"})

    assert result.name == "boss (2).png"


def test_delete_image_thumbnails_removes_registered_and_fallback_thumbnail(tmp_path: Path):
    registered = tmp_path / "legacy" / "alice.jpg"
    fallback = tmp_path / "characters" / "thumb" / "alice.jpg"
    registered.parent.mkdir(parents=True)
    fallback.parent.mkdir(parents=True)
    registered.write_bytes(b"registered")
    fallback.write_bytes(b"fallback")

    deleted = _delete_image_thumbnails(
        tmp_path,
        "characters/alice.png",
        "legacy/alice.jpg",
    )

    assert deleted == 2
    assert not registered.exists()
    assert not fallback.exists()


def test_delete_image_thumbnails_does_not_leave_folder_root(tmp_path: Path):
    outside = tmp_path.parent / "outside-thumbnail.jpg"
    outside.write_bytes(b"keep")
    try:
        deleted = _delete_image_thumbnails(tmp_path, "missing.png", str(outside))
        assert deleted == 0
        assert outside.exists()
    finally:
        outside.unlink(missing_ok=True)


def test_collapse_organizer_move_sources_deduplicates_and_omits_selected_descendants():
    result = _collapse_organizer_move_sources(
        ["Personajes/Alice", "Personajes", "Personajes/Alice/Rostros", "Generales", "Generales"],
    )

    assert result == ["Generales", "Personajes"]


def test_collapse_organizer_move_sources_keeps_independent_siblings():
    result = _collapse_organizer_move_sources(
        ["Personajes/Alice", "Personajes/Boss", "Generales/Testing"],
    )

    assert result == ["Generales/Testing", "Personajes/Alice", "Personajes/Boss"]
