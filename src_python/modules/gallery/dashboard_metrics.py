from __future__ import annotations

from pathlib import PurePosixPath


def normalize_rel_path(path: str | None) -> str:
    if not path:
        return ""
    return str(path).replace("\\", "/").strip("/")


def classify_folder_type_from_rel_path(path: str | None) -> str:
    rel = normalize_rel_path(path).lower()
    if not rel:
        return "Otros"
    segments = [seg for seg in rel.split("/") if seg]
    aliases: dict[str, tuple[str, ...]] = {
        "Safe": ("safe",),
        "NoSafe": ("nosafe", "no-safe", "nsfw"),
        "FaceDetail": ("facedetail", "face-detail", "face_detail"),
        "Upscale": ("upscale", "upscaled"),
    }
    for segment in segments:
        for label, keys in aliases.items():
            if segment in keys:
                return label
    return "Otros"


def is_root_image_path(path: str | None) -> bool:
    rel = normalize_rel_path(path)
    if not rel:
        return True
    parent = str(PurePosixPath(rel).parent)
    return parent in ("", ".")
