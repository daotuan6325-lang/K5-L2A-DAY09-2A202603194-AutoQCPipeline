"""Test cho check thưởng aspect_ratio (học viên viết). Ảnh giả 320x240 (xem conftest.make_ds)."""
from pipeline.checks import aspect_ratio


def find(issues, code=None):
    return [(i.image, i.line) for i in issues if code is None or i.code == code]


def people(n, w=0.1, h=0.3):
    """n box person đứng: rộng 0.1*320=32px, cao 0.3*240=72px -> r ≈ 0.44; lệch nhẹ để MAD > 0."""
    return [f"1 0.5 0.5 {w + 0.002 * k:.3f} {h}" for k in range(n)]


def test_normal_boxes_are_silent(make_ds, cfg):
    ds = make_ds(images={"a": 1}, labels={"a": people(10) + ["0 0.5 0.5 0.3 0.2"]})
    assert aspect_ratio.run(ds, cfg) == []


def test_extreme_aspect_is_flagged_whatever_the_class(make_ds, cfg):
    # 0.9*320 = 288px rộng, 0.02*240 = 4.8px cao -> r = 60 > 8
    ds = make_ds(images={"a": 1}, labels={"a": ["0 0.5 0.5 0.3 0.2", "2 0.5 0.5 0.9 0.02"]})
    iss = aspect_ratio.run(ds, cfg)
    assert find(iss, "BOX_EXTREME_ASPECT") == [("a", 2)]
    assert all(i.severity == "warn" for i in iss) and iss[0].extra["aspect"] > 8


def test_person_shaped_like_a_car_is_an_outlier(make_ds, cfg):
    # 10 person đứng (r≈0.44) + 1 person nằm ngang r = (0.6*320)/(0.2*240) = 4 (< 8 nên không phải EXTREME)
    ds = make_ds(images={"a": 1}, labels={"a": people(10) + ["1 0.5 0.5 0.6 0.2"]})
    iss = aspect_ratio.run(ds, cfg)
    assert find(iss) == [("a", 11)] and iss[0].code == "BOX_ASPECT_OUTLIER" and iss[0].extra["z"] > 0


def test_same_shape_in_another_class_is_fine(make_ds, cfg):
    # car r = 4 là bình thường; car chỉ có 1 box (< min_class_boxes) nên không tính thống kê lớp car
    ds = make_ds(images={"a": 1}, labels={"a": people(10) + ["0 0.5 0.5 0.6 0.2"]})
    assert aspect_ratio.run(ds, cfg) == []


def test_class_with_too_few_boxes_gets_no_outlier_test(make_ds, cfg):
    ds = make_ds(images={"a": 1}, labels={"a": people(3) + ["1 0.5 0.5 0.6 0.2"]})
    assert aspect_ratio.run(ds, cfg) == []


def test_statistics_pool_all_images_and_line_numbers_survive_blank_and_broken_lines(make_ds, cfg):
    ds = make_ds(images={"a": 1, "b": 2}, labels={"a": people(6), "b": people(4) + ["", "garbage", "93 0.5 0.5 0.1 0.1", "1 0.5 0.5 0.6 0.2"]})
    assert find(aspect_ratio.run(ds, cfg)) == [("b", 8)]


def test_thresholds_come_from_config(make_ds, cfg):
    ds = make_ds(images={"a": 1}, labels={"a": ["0 0.5 0.5 0.6 0.2"]})          # r = 4
    assert aspect_ratio.run(ds, cfg) == []
    cfg["aspect_ratio"] = {"max_aspect": 3.0}
    assert find(aspect_ratio.run(ds, cfg), "BOX_EXTREME_ASPECT") == [("a", 1)]


def test_box_cut_by_the_image_border_is_skipped(make_ds, cfg):
    # person "dẹt" giống lỗi, nhưng chạm mép trên (y - h/2 = 0): người bị khung ảnh cắt, không phải lỗi box
    ds = make_ds(images={"a": 1}, labels={"a": people(10) + ["1 0.5 0.03 0.6 0.06", "1 0.5 0.5 0.6 0.2"]})
    assert find(aspect_ratio.run(ds, cfg)) == [("a", 12)]            # chỉ box KHÔNG chạm mép bị cờ


def test_corrupt_image_and_orphan_label_are_skipped(make_ds, cfg):
    ds = make_ds(images={"a": b"not an image"}, labels={"a": ["2 0.5 0.5 0.9 0.02"], "ghost": ["2 0.5 0.5 0.9 0.02"]})
    assert aspect_ratio.run(ds, cfg) == []
