"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401

NAME = "label_format"


def _overflow(cx, cy, w, h):
    """Mức tràn lớn nhất của 4 mép box ra ngoài [0, 1] (0 nếu nằm trong ảnh)."""
    x1, x2, y1, y2 = cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2
    return max(0.0, -x1, x2 - 1.0, -y1, y2 - 1.0)


def run(ds, cfg):
    c = cfg["label_format"]
    tol, min_px, max_frac, dup_iou = c["overflow_tol"], c["min_box_px"], c["max_box_frac"], c["dup_box_iou"]
    n_cls = len(ds.classes)
    issues = []

    for lp in ds.label_files():
        stem = lp.stem
        size = ds.image_size(stem) if ds.image_path(stem) else None    # nhãn mồ côi: không có ảnh -> bỏ kiểm px
        prev = []                                                       # các box hợp lệ ở dòng TRƯỚC: (lineno, box)

        for ln, text in ds.read_label_lines(stem) or []:
            def add(sev, code, msg, **extra):
                issues.append(Issue(NAME, sev, code, stem, msg, ln, extra))

            try:
                cls, x, y, w, h = parse_yolo_line(text)
            except ValueError as e:
                add(ERROR, "BAD_FORMAT", f"dòng không đúng 5 cột số ({e}): {text.strip()!r}")
                continue
            if not 0 <= cls < n_cls:
                add(ERROR, "BAD_CLASS_ID", f"id lớp {cls} ngoài 0..{n_cls - 1}", cls=cls)
                continue
            if w <= 0 or h <= 0:
                add(ERROR, "BOX_ZERO", f"box rộng/cao <= 0 (w={w}, h={h})")
                continue

            over = _overflow(x, y, w, h)
            if over > tol:
                add(ERROR, "BOX_OUT_OF_IMAGE", f"box tràn ảnh {over:.4f} > {tol}", overflow=round(over, 6))

            box = (x, y, w, h)
            for pln, pbox in prev:
                if pbox[0] == cls:
                    iou = iou_xywh(box, pbox[1:])
                    if iou > dup_iou:
                        add(ERROR, "DUP_BOX", f"trùng box ở dòng {pln} (IoU={iou:.3f})", dup_of=pln, iou=round(iou, 4))
                        break
            prev.append((ln, (cls, *box)))

            if size:
                W, H = size
                short = min(w * W, h * H)
                if short < min_px:
                    add(WARN, "BOX_TINY", f"cạnh ngắn {short:.1f}px < {min_px}px", short_px=round(short, 1))
            if w * h > max_frac:
                add(WARN, "BOX_HUGE", f"box chiếm {w * h:.2%} ảnh > {max_frac:.0%}", frac=round(w * h, 4))

    return issues
