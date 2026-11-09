from pathlib import Path

from src_python.modules.gallery.service import GalleryService


def test_folder_walk_keeps_empty_directories_and_skips_thumb_branches(tmp_path: Path) -> None:
    (tmp_path / "Personajes" / "Alice" / "Safe").mkdir(parents=True)
    (tmp_path / "Personajes" / "Alice" / "thumb" / "nested").mkdir(parents=True)
    (tmp_path / "Personajes" / "Alice" / "Safe" / "image.png").write_bytes(b"image")
    (tmp_path / "Personajes" / "Alice" / "thumb" / "preview.jpg").write_bytes(b"thumb")

    directories, files = GalleryService._walk_folder_without_thumbnails(tmp_path)

    assert directories == ["Personajes", "Personajes/Alice", "Personajes/Alice/Safe"]
    assert [path.relative_to(tmp_path).as_posix() for path in files] == [
        "Personajes/Alice/Safe/image.png"
    ]


def test_thumbnail_path_detection_is_case_insensitive() -> None:
    assert GalleryService._is_thumbnail_relative_path("Alice/thumb/image.jpg")
    assert GalleryService._is_thumbnail_relative_path("Alice/THUMB/nested/image.jpg")
    assert not GalleryService._is_thumbnail_relative_path("Alice/thumbnail/image.jpg")
