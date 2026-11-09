"""Tests for gallery naming_plan (pure rename planning)."""

import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src_python.modules.gallery.naming_plan import (
    ImageRow,
    NamingPlanError,
    build_rename_plan,
    classify_stem,
    compute_next_index,
    ImageNameClass,
)


def test_classify_correct_related_unrelated() -> None:
    base = "Alice"
    width = 4
    assert classify_stem("Alice_0001", base, width) == ImageNameClass.CORRECT
    assert classify_stem("ALIce_0001", base, width) == ImageNameClass.RELATED
    assert classify_stem("alice_2", base, width) == ImageNameClass.RELATED
    assert classify_stem("alice_final", base, width) == ImageNameClass.RELATED
    assert classify_stem("alice", base, width) == ImageNameClass.RELATED
    assert classify_stem("andres_01", base, width) == ImageNameClass.UNRELATED


def test_next_index_from_correct_only() -> None:
    rows = [
        ImageRow(1, "Alice_0001.png"),
        ImageRow(2, "Alice_0100.png"),
        ImageRow(3, "ALIce_01.png"),
    ]
    assert compute_next_index(rows, "Alice", 4) == 101


def test_full_folder_related_then_unrelated() -> None:
    rows = [
        ImageRow(1, "Alice_0001.png"),
        ImageRow(2, "Alice_0100.png"),
        ImageRow(3, "ALIce_01.png"),
        ImageRow(4, "alice_final.png"),
        ImageRow(5, "andres.png"),
        ImageRow(6, "foto_final.png"),
    ]
    plan = build_rename_plan(
        naming_base="Alice",
        naming_number_width=4,
        all_rows=rows,
        mode="all",
        selected_ids=None,
    )
    assert plan.next_counter_start == 101
    assert plan.related_count == 2
    assert plan.unrelated_count == 2
    assert plan.unchanged_count == 2
    by_id = {e.image_id: e for e in plan.entries}
    assert by_id[1].reason == "unchanged"
    assert by_id[2].reason == "unchanged"
    assert by_id[3].new_path == "Alice_0101.png"
    assert by_id[4].new_path == "Alice_0102.png"
    assert by_id[5].new_path == "Alice_0103.png"
    assert by_id[6].new_path == "Alice_0104.png"


def test_selected_mode_uses_global_counter() -> None:
    rows = [
        ImageRow(1, "Alice_0001.png"),
        ImageRow(2, "Alice_0100.png"),
        ImageRow(3, "andres.png"),
        ImageRow(4, "foto.png"),
    ]
    plan = build_rename_plan(
        naming_base="Alice",
        naming_number_width=4,
        all_rows=rows,
        mode="selected",
        selected_ids=frozenset({3, 4}),
    )
    by_id = {e.image_id: e for e in plan.entries}
    assert by_id[3].new_path == "Alice_0101.png"
    assert by_id[4].new_path == "Alice_0102.png"
    assert by_id[1].reason == "unchanged"
    assert by_id[2].reason == "unchanged"


def test_selected_correct_only_no_renames() -> None:
    rows = [ImageRow(1, "Alice_0001.png"), ImageRow(2, "wrong.png")]
    plan = build_rename_plan(
        naming_base="Alice",
        naming_number_width=4,
        all_rows=rows,
        mode="selected",
        selected_ids=frozenset({1}),
    )
    assert all(e.reason == "unchanged" for e in plan.entries)


def test_preserves_subdirectory() -> None:
    rows = [
        ImageRow(1, "sub/ALIce_01.png"),
        ImageRow(2, "sub/other.png"),
    ]
    plan = build_rename_plan(
        naming_base="Alice",
        naming_number_width=4,
        all_rows=rows,
        mode="all",
        selected_ids=None,
    )
    by_id = {e.image_id: e for e in plan.entries}
    assert by_id[1].new_path == "sub/Alice_0001.png"
    assert by_id[2].new_path == "sub/Alice_0002.png"


def test_selected_requires_ids() -> None:
    with pytest.raises(NamingPlanError):
        build_rename_plan(
            naming_base="Alice",
            naming_number_width=4,
            all_rows=[ImageRow(1, "a.png")],
            mode="selected",
            selected_ids=frozenset(),
        )


def test_invalid_config() -> None:
    with pytest.raises(NamingPlanError):
        build_rename_plan(
            naming_base="",
            naming_number_width=4,
            all_rows=[ImageRow(1, "a.png")],
            mode="all",
            selected_ids=None,
        )
