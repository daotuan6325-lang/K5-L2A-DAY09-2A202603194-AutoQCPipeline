"""CHECK THƯỞNG — Tỉ lệ khung hình (rộng/cao, tính theo PIXEL) bất thường của box.   (học viên viết thêm)

Test:  pytest tests/test_aspect_ratio.py -q
Chạy riêng trên một dataset:  python -m pipeline.checks.aspect_ratio data/raw

Ý tưởng: box của cùng một lớp có hình dạng khá ổn định (person thường đứng => cao hơn rộng; car/bus thường rộng hơn cao).
Box "dẹt như sợi chỉ" hoặc person có hình dạng giống ô tô thường là dấu hiệu box vẽ hỏng, box lỏng một chiều, hoặc gán nhầm lớp.
Máy không biết chắc => chỉ CẢNH BÁO (WARN), người xem.

| code               | severity | khi nào                                                                                   |
|--------------------|----------|-------------------------------------------------------------------------------------------|
| BOX_EXTREME_ASPECT | WARN     | max(r, 1/r) > `max_aspect`, với r = (w*W) / (h*H)   (bất kể lớp)                          |
| BOX_ASPECT_OUTLIER | WARN     | |z| > `z_thresh`, z = 0,6745 * (log r - median_lớp) / max(MAD_lớp, `min_mad`)             |
|                    |          | (median/MAD tính trên CHÍNH dataset, chỉ khi lớp có >= `min_class_boxes` box hợp lệ)        |

- Mỗi box tối đa MỘT issue (EXTREME ưu tiên hơn OUTLIER). Thứ tự: theo file nhãn rồi theo số dòng gốc.
- Dùng log(r) để 2 chiều đối xứng (rộng gấp 3 và cao gấp 3 cách median như nhau). MAD (median absolute deviation)
  bền với chính các box lỗi, khác với trung bình/độ lệch chuẩn bị box lỗi kéo lệch.
- Ngưỡng đọc từ `cfg["aspect_ratio"]`. Khoá này KHÔNG có trong configs/pipeline.yaml (file cấu hình bị ghim, không được thêm mục),
  nên có giá trị mặc định ở `DEFAULTS`; muốn đổi thì truyền cfg khác (test làm vậy).
- Box chạm mép ảnh (cách mép < `edge_tol`) bị BỎ QUA hoàn toàn (không cờ, không tính vào median): vật bị khung ảnh cắt
  thì hình dạng box không còn nói lên gì. Lý do có bằng chứng: chạy thử trên raw, 5/6 cờ ban đầu là người bị mép ảnh cắt.
- Dòng hỏng / id lớp lạ / box rỗng: bỏ qua (label_format đã báo), không làm chết script. Ảnh không mở được: bỏ qua.
"""
from __future__ import annotations

import math
import statistics
import sys
from collections import defaultdict

from ..common import WARN, Issue, parse_yolo_line

NAME = "aspect_ratio"
DEFAULTS = {"max_aspect": 8.0, "z_thresh": 3.5, "min_class_boxes": 8, "min_mad": 0.1, "edge_tol": 0.01}


def _boxes(ds, edge_tol=DEFAULTS["edge_tol"]):
    """[(stem, số dòng gốc, lớp, tỉ lệ r theo pixel)] của các box hợp lệ, KHÔNG chạm mép ảnh."""
    out = []
    for lp in ds.label_files():
        stem = lp.stem
        size = ds.image_size(stem) if ds.image_path(stem) else None
        if not size:
            continue
        W, H = size
        for ln, text in ds.read_label_lines(stem) or []:
            try:
                cls, x, y, w, h = parse_yolo_line(text)
            except ValueError:
                continue
            if not 0 <= cls < len(ds.classes) or w <= 0 or h <= 0:
                continue
            if min(x - w / 2, 1 - (x + w / 2), y - h / 2, 1 - (y + h / 2)) < edge_tol:
                continue                                   # bị khung ảnh cắt (hoặc tràn): hình dạng không đáng tin
            out.append((stem, ln, cls, (w * W) / (h * H)))
    return out


def run(ds, cfg):
    c = {**DEFAULTS, **(cfg.get("aspect_ratio") or {})}
    boxes = _boxes(ds, c["edge_tol"])

    by_cls = defaultdict(list)
    for _, _, cls, r in boxes:
        by_cls[cls].append(math.log(r))
    stats = {}
    for cls, logs in by_cls.items():
        if len(logs) >= c["min_class_boxes"]:
            med = statistics.median(logs)
            mad = statistics.median(abs(x - med) for x in logs)
            stats[cls] = (med, max(mad, c["min_mad"]))

    issues = []
    for stem, ln, cls, r in boxes:
        name = ds.classes[cls]
        if max(r, 1 / r) > c["max_aspect"]:
            issues.append(Issue(NAME, WARN, "BOX_EXTREME_ASPECT", stem,
                                f"box {name} tỉ lệ rộng/cao {r:.2f} (lệch > {c['max_aspect']:g} lần)", ln,
                                {"aspect": round(r, 3)}))
            continue
        if cls in stats:
            med, mad = stats[cls]
            z = 0.6745 * (math.log(r) - med) / mad
            if abs(z) > c["z_thresh"]:
                issues.append(Issue(NAME, WARN, "BOX_ASPECT_OUTLIER", stem,
                                    f"box {name} tỉ lệ rộng/cao {r:.2f}, khác hẳn {name} điển hình ({math.exp(med):.2f}); z={z:.1f}", ln,
                                    {"aspect": round(r, 3), "class_median": round(math.exp(med), 3), "z": round(z, 2)}))
    return issues


if __name__ == "__main__":                       # chạy thử: python -m pipeline.checks.aspect_ratio data/raw
    from collections import Counter

    from ..common import Dataset, load_config
    cfg = load_config()
    ds = Dataset(sys.argv[1] if len(sys.argv) > 1 else "data/raw", cfg["classes"])
    iss = run(ds, cfg)
    print(f"ảnh có nhãn: {len(ds.label_files())}; box hợp lệ không chạm mép: {len(_boxes(ds))}; issue: {len(iss)} {dict(Counter(i.code for i in iss))}")
    for i in iss:
        print(f"  {i.code:20} {i.image}:{i.line}  {i.message}")
