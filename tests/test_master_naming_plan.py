from src_python.modules.gallery.naming_plan import ImageRow, build_missing_naming_plan


def test_missing_naming_plan_preserves_valid_names_and_continues_counter():
    plan = build_missing_naming_plan(
        folder_name="Juanito",
        all_rows=[
            ImageRow(id=1, path="Juanito_01.png"),
            ImageRow(id=2, path="juanito_007.jpg"),
            ImageRow(id=3, path="ComfyUI_00001.png"),
            ImageRow(id=4, path="otra.webp"),
        ],
    )

    assert plan.unchanged_count == 2
    assert plan.number_width == 3
    assert [(entry.image_id, entry.new_path) for entry in plan.entries] == [
        (3, "juanito_008.png"),
        (4, "juanito_009.webp"),
    ]


def test_missing_naming_plan_uses_each_images_existing_parent():
    plan = build_missing_naming_plan(
        folder_name="Alice",
        all_rows=[
            ImageRow(id=10, path="Personajes/Alice/Alice_01.png"),
            ImageRow(id=11, path="Personajes/Alice/base.png"),
        ],
    )

    assert len(plan.entries) == 1
    assert plan.entries[0].new_path == "Personajes/Alice/alice_02.png"


def test_missing_naming_plan_uses_the_same_safe_prefix_as_organizer():
    plan = build_missing_naming_plan(
        folder_name="Damien Cross",
        all_rows=[
            ImageRow(id=20, path="Damien Cross/damien_cross_01.png"),
            ImageRow(id=21, path="Damien Cross/base.png"),
        ],
    )

    assert plan.unchanged_count == 1
    assert plan.entries[0].new_path == "Damien Cross/damien_cross_02.png"
