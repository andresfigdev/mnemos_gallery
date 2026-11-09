from src_python.modules.gallery.dashboard_metrics import classify_folder_type_from_rel_path


def test_classify_folder_type_safe() -> None:
    assert classify_folder_type_from_rel_path("Safe/Marta_00001.png") == "Safe"


def test_classify_folder_type_nosafe_aliases() -> None:
    assert classify_folder_type_from_rel_path("NoSafe/Alice_00001.png") == "NoSafe"
    assert classify_folder_type_from_rel_path("nsfw/Alice_00001.png") == "NoSafe"


def test_classify_folder_type_facedetail_and_upscale() -> None:
    assert classify_folder_type_from_rel_path("FaceDetail/shot.png") == "FaceDetail"
    assert classify_folder_type_from_rel_path("upscale/result.png") == "Upscale"


def test_classify_folder_type_other_when_missing_match() -> None:
    assert classify_folder_type_from_rel_path("Random/set/image.png") == "Otros"
    assert classify_folder_type_from_rel_path("") == "Otros"
