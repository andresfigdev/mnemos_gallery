"""
Pure planning logic for folder image naming (no I/O).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePath
from typing import Literal, Sequence


class NamingPlanError(Exception):
    """Raised when a rename plan cannot be built (e.g. collisions)."""


class ImageNameClass(str, Enum):
    CORRECT = "correct"
    RELATED = "related"
    UNRELATED = "unrelated"


RenameReason = Literal["unchanged", "rename"]


@dataclass(frozen=True, slots=True)
class ImageRow:
    id: int
    path: str


@dataclass(frozen=True, slots=True)
class NamingPlanEntry:
    image_id: int
    old_path: str
    new_path: str | None
    reason: RenameReason
    name_class: ImageNameClass | None


@dataclass(frozen=True, slots=True)
class NamingPlanResult:
    entries: tuple[NamingPlanEntry, ...]
    next_counter_start: int
    related_count: int
    unrelated_count: int
    unchanged_count: int


@dataclass(frozen=True, slots=True)
class MissingNamingPlanResult:
    """Plan that preserves every image already named ``folder_<number>``."""

    entries: tuple[NamingPlanEntry, ...]
    unchanged_count: int
    number_width: int
    next_counter_start: int


def _stem_suffix(rel_path: str) -> tuple[str, str, str]:
    """Returns (stem, parent_posix, suffix) using forward slashes for parent."""
    p = PurePath(rel_path)
    parent = p.parent
    parent_s = "" if str(parent) in (".", "") else str(parent).replace("\\", "/")
    return p.stem, parent_s, p.suffix


def _correct_number(stem: str, base: str, width: int) -> int | None:
    pattern = re.compile(rf"^{re.escape(base)}_(\d{{{int(width)}}})$")
    m = pattern.fullmatch(stem)
    if not m:
        return None
    return int(m.group(1))


def _is_related(stem: str, base: str) -> bool:
    b = base.lower()
    s = stem.lower()
    if s == b:
        return True
    prefix = b + "_"
    return s.startswith(prefix)


def classify_stem(stem: str, base: str, width: int) -> ImageNameClass:
    if _correct_number(stem, base, width) is not None:
        return ImageNameClass.CORRECT
    if _is_related(stem, base):
        return ImageNameClass.RELATED
    return ImageNameClass.UNRELATED


def compute_next_index(all_rows: Sequence[ImageRow], base: str, width: int) -> int:
    best = 0
    for row in all_rows:
        stem, _parent, _suf = _stem_suffix(row.path)
        n = _correct_number(stem, base, width)
        if n is not None:
            best = max(best, n)
    return best + 1


def build_rename_plan(
    *,
    naming_base: str,
    naming_number_width: int,
    all_rows: Sequence[ImageRow],
    mode: Literal["all", "selected"],
    selected_ids: frozenset[int] | None,
) -> NamingPlanResult:
    base = naming_base.strip()
    width = int(naming_number_width)
    if not base or width < 1:
        raise NamingPlanError("naming_base must be non-empty and naming_number_width >= 1")

    by_id: dict[int, str] = {r.id: r.path for r in all_rows}
    if mode == "selected":
        if not selected_ids:
            raise NamingPlanError("selected_ids is required for mode=selected")
        missing = selected_ids - by_id.keys()
        if missing:
            raise NamingPlanError(f"Unknown image ids: {sorted(missing)}")

    candidate_ids: set[int]
    if mode == "all":
        candidate_ids = set(by_id)
    else:
        candidate_ids = set(selected_ids or ())

    next_index = compute_next_index(all_rows, base, width)

    to_renumber: list[tuple[int, str, ImageNameClass]] = []
    for rid in sorted(candidate_ids, key=lambda i: by_id[i].lower()):
        path = by_id[rid]
        stem, _parent, _suf = _stem_suffix(path)
        cls = classify_stem(stem, base, width)
        if cls == ImageNameClass.CORRECT:
            continue
        to_renumber.append((rid, path, cls))

    related = [(rid, p, c) for rid, p, c in to_renumber if c == ImageNameClass.RELATED]
    unrelated = [(rid, p, c) for rid, p, c in to_renumber if c == ImageNameClass.UNRELATED]

    def sort_key(item: tuple[int, str, ImageNameClass]) -> tuple[str, int]:
        return (item[1].lower(), item[0])

    related.sort(key=sort_key)
    unrelated.sort(key=sort_key)

    ordered = related + unrelated

    proposed: dict[int, str] = {}
    counter = next_index
    for rid, old_path, _cls in ordered:
        _stem, parent, suffix = _stem_suffix(old_path)
        stem_new = f"{base}_{str(counter).zfill(width)}"
        counter += 1
        if parent:
            new_path = f"{parent}/{stem_new}{suffix}"
        else:
            new_path = f"{stem_new}{suffix}"
        proposed[rid] = new_path.replace("\\", "/")

    final_paths: dict[int, str] = dict(by_id)
    for rid, new_p in proposed.items():
        final_paths[rid] = new_p

    seen: set[str] = set()
    for rid, final_p in final_paths.items():
        if final_p in seen:
            raise NamingPlanError(f"Duplicate final path after plan: {final_p}")
        seen.add(final_p)

    cls_by_renumbered_id: dict[int, ImageNameClass] = {rid: c for rid, _p, c in to_renumber}

    entries: list[NamingPlanEntry] = []
    related_count = 0
    unrelated_count = 0
    unchanged_count = 0
    for row in sorted(all_rows, key=lambda r: (r.path.lower(), r.id)):
        rid = row.id
        old_path = row.path
        if rid in proposed:
            new_p = proposed[rid]
            cls = cls_by_renumbered_id[rid]
            if cls == ImageNameClass.RELATED:
                related_count += 1
            else:
                unrelated_count += 1
            entries.append(
                NamingPlanEntry(
                    image_id=rid,
                    old_path=old_path,
                    new_path=new_p,
                    reason="rename",
                    name_class=cls,
                )
            )
        else:
            unchanged_count += 1
            stem, _parent, _suf = _stem_suffix(old_path)
            cls = classify_stem(stem, base, width)
            entries.append(
                NamingPlanEntry(
                    image_id=rid,
                    old_path=old_path,
                    new_path=None,
                    reason="unchanged",
                    name_class=cls,
                )
            )

    return NamingPlanResult(
        entries=tuple(entries),
        next_counter_start=next_index,
        related_count=related_count,
        unrelated_count=unrelated_count,
        unchanged_count=unchanged_count,
    )


def plan_to_path_map(result: NamingPlanResult) -> dict[int, str]:
    """id -> final relative path."""
    return {e.image_id: e.new_path if e.new_path is not None else e.old_path for e in result.entries}


def build_missing_naming_plan(
    *,
    folder_name: str,
    all_rows: Sequence[ImageRow],
    minimum_width: int = 2,
) -> MissingNamingPlanResult:
    """Rename only files that do not already follow ``folder_<digits>``.

    Existing counters are accepted with any width so a maintenance pass never
    rewrites valid names merely because an older folder used two or three
    digits. New names continue after the greatest existing counter.
    """
    base = re.sub(r"[^\w-]+", "_", folder_name.strip(), flags=re.UNICODE).strip("_-.").lower()
    if not base:
        raise NamingPlanError("folder_name must be non-empty")

    pattern = re.compile(rf"^{re.escape(base)}_(\d+)$", re.IGNORECASE)
    correct_ids: set[int] = set()
    greatest = 0
    width = max(1, int(minimum_width))

    for row in all_rows:
        stem, _parent, _suffix = _stem_suffix(row.path)
        match = pattern.fullmatch(stem)
        if not match:
            continue
        digits = match.group(1)
        correct_ids.add(row.id)
        greatest = max(greatest, int(digits))
        width = max(width, len(digits))

    candidates = sorted(
        (row for row in all_rows if row.id not in correct_ids),
        key=lambda row: (row.path.casefold(), row.id),
    )
    used_paths = {row.path.replace("\\", "/").casefold() for row in all_rows}
    entries: list[NamingPlanEntry] = []
    counter = greatest + 1

    for row in candidates:
        _stem, parent, suffix = _stem_suffix(row.path)
        while True:
            new_stem = f"{base}_{str(counter).zfill(width)}"
            counter += 1
            new_path = f"{parent}/{new_stem}{suffix}" if parent else f"{new_stem}{suffix}"
            normalized = new_path.replace("\\", "/")
            if normalized.casefold() not in used_paths:
                used_paths.add(normalized.casefold())
                break
        entries.append(
            NamingPlanEntry(
                image_id=row.id,
                old_path=row.path.replace("\\", "/"),
                new_path=normalized,
                reason="rename",
                name_class=ImageNameClass.UNRELATED,
            )
        )

    return MissingNamingPlanResult(
        entries=tuple(entries),
        unchanged_count=len(correct_ids),
        number_width=width,
        next_counter_start=greatest + 1,
    )
