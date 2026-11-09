import json
import math

from src_python.modules.gallery.service import build_location_guid, sanitize_json_for_database


def test_sanitize_json_for_database_replaces_non_finite_numbers_recursively():
    source = {
        "normal": 1.25,
        "nested": [float("nan"), {"positive": float("inf"), "negative": -float("inf")}],
        "tuple": (2, float("nan")),
    }

    sanitized = sanitize_json_for_database(source)

    assert sanitized == {
        "normal": 1.25,
        "nested": [None, {"positive": None, "negative": None}],
        "tuple": [2, None],
    }
    assert math.isfinite(sanitized["normal"])
    json.dumps(sanitized, allow_nan=False)


def test_sanitize_json_for_database_does_not_mutate_source():
    source = {"value": float("nan")}

    sanitize_json_for_database(source)

    assert math.isnan(source["value"])


def test_build_location_guid_is_stable_and_distinguishes_locations():
    content_guid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    first = build_location_guid(content_guid, "folder-a", "Selene_210.png")
    same = build_location_guid(content_guid, "folder-a", "Selene_210.png")
    other = build_location_guid(content_guid, "folder-b", "Selene_210.png")

    assert first == same
    assert first != other
    assert len(first) == 36
