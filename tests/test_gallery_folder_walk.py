import os
from datetime import datetime, timedelta
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


def test_unchanged_image_is_skipped_when_file_and_thumbnail_are_current(tmp_path: Path) -> None:
    image_path = tmp_path / "Alice" / "alice_01.png"
    thumb_path = tmp_path / "Alice" / "thumb" / "alice_01.jpg"
    image_path.parent.mkdir(parents=True)
    thumb_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"image")
    thumb_path.write_bytes(b"thumb")
    last_scan = datetime.now()
    old_timestamp = (last_scan - timedelta(minutes=5)).timestamp()
    os.utime(image_path, (old_timestamp, old_timestamp))

    assert GalleryService._can_skip_unchanged_image(
        file_path=image_path,
        folder_path=tmp_path,
        existing={
            "size": image_path.stat().st_size,
            "thumb_path": "Alice/thumb/alice_01.jpg",
            "folder_node_id": 10,
            "guid": "existing-guid",
        },
        last_scan_at=last_scan,
        folder_node_id=10,
    )


def test_changed_image_is_not_skipped(tmp_path: Path) -> None:
    image_path = tmp_path / "alice_01.png"
    thumb_path = tmp_path / "thumb" / "alice_01.jpg"
    thumb_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"new-image")
    thumb_path.write_bytes(b"thumb")
    last_scan = datetime.now() - timedelta(minutes=5)

    assert not GalleryService._can_skip_unchanged_image(
        file_path=image_path,
        folder_path=tmp_path,
        existing={
            "size": image_path.stat().st_size,
            "thumb_path": "thumb/alice_01.jpg",
            "folder_node_id": 10,
            "guid": "existing-guid",
        },
        last_scan_at=last_scan,
        folder_node_id=10,
    )


def test_missing_images_are_derived_from_the_completed_folder_walk() -> None:
    existing = {
        "Alice/alice_01.png": {
            "id": 1,
            "guid": "alice-guid",
            "folder_id": "root-id",
            "thumb_path": "Alice/thumb/alice_01.jpg",
        },
        "Boss/boss_01.png": {
            "id": 2,
            "guid": "boss-guid",
            "folder_id": "root-id",
            "thumb_path": "Boss/thumb/boss_01.jpg",
        },
    }

    missing = GalleryService._find_missing_images_from_scan(
        existing,
        ["Alice/alice_01.png"],
    )

    assert missing == [{
        "id": 2,
        "guid": "boss-guid",
        "path": "Boss/boss_01.png",
        "folder_id": "root-id",
        "thumb_path": "Boss/thumb/boss_01.jpg",
        "reason": "not_exists",
    }]
