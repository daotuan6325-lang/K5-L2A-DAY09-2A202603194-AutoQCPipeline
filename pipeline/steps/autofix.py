"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict  # noqa: F401

import yaml  # noqa: F401

from ..common import ERROR, parse_yolo_line  # noqa: F401

DROP_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
CLIP_CODES = {"BOX_OUT_OF_IMAGE"}
REMOVE_CODES = {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}       # + mọi mã bắt đầu bằng DUP_IMAGE_


def _is_remove(code):
    return code in REMOVE_CODES or code.startswith("DUP_IMAGE_")


def _clip(text):
    """Cắt box về [0,1]. Trả dòng mới, hoặc None nếu box không còn diện tích (hoặc không parse được)."""
    try:
        cls, x, y, w, h = parse_yolo_line(text)
    except ValueError:
        return None
    x1, x2 = max(0.0, x - w / 2), min(1.0, x + w / 2)
    y1, y2 = max(0.0, y - h / 2), min(1.0, y + h / 2)
    if x2 - x1 <= 0 or y2 - y1 <= 0:
        return None
    return f"{cls} {(x1 + x2) / 2:.6f} {(y1 + y2) / 2:.6f} {x2 - x1:.6f} {y2 - y1:.6f}"


def _rename_classes(ds, cfg):
    data = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) if ds.yaml_path.exists() else {}
    data = data or {}
    before = data.get("names")
    after = {i: n for i, n in enumerate(cfg["classes"])}
    data["names"] = after
    if "nc" in data:
        data["nc"] = len(cfg["classes"])
    ds.yaml_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return dict(image="data.yaml", line="", action="rename_classes", before=str(before), after=str(after))


def fix(ds, issues, cfg):
    errors = [i for i in issues if i.severity == ERROR]
    fixes = []

    # 1) Cấp dataset: data.yaml
    if any(i.code == "BAD_CLASS_NAME" for i in errors):
        fixes.append(_rename_classes(ds, cfg))

    # 2) Cấp ảnh: xoá ảnh + nhãn (trùng, rò rỉ test, hỏng, sai kích thước)
    removed = set()
    for i in errors:
        if not _is_remove(i.code) or i.image in removed:
            continue
        img = ds.image_path(i.image)
        lab = ds.label_path(i.image)
        if img is None and not lab.exists():
            continue                                   # đã xoá ở lần chạy trước -> idempotent
        before = img.name if img else "(không có ảnh)"
        if img is not None:
            img.unlink()
        if lab.exists():
            lab.unlink()
        removed.add(i.image)
        fixes.append(dict(image=i.image, line="", action="remove_image", before=before, after=f"(xoá: {i.code})"))

    # 3) Cấp dòng: gom theo file, quyết định theo SỐ DÒNG GỐC, ghi lại MỘT lần
    per_file = defaultdict(dict)                         # stem -> {line: "drop" | "clip"}
    for i in errors:
        if i.line in (None, "") or i.image in removed:
            continue
        if i.code in DROP_CODES:
            per_file[i.image][int(i.line)] = "drop"         # xoá thắng cắt
        elif i.code in CLIP_CODES:
            per_file[i.image].setdefault(int(i.line), "clip")

    for stem, actions in per_file.items():
        lp = ds.label_path(stem)
        if not lp.exists():
            continue
        raw = lp.read_text(encoding="utf-8", errors="replace").splitlines()
        out, changes = [], []
        for ln, text in enumerate(raw, 1):                  # dòng trống vẫn đếm -> khớp số dòng gốc
            act = actions.get(ln)
            if act is None or not text.strip():
                out.append(text)
                continue
            if act == "clip":
                new = _clip(text)
                if new is not None:
                    out.append(new)
                    changes.append(dict(image=stem, line=ln, action="clip_box", before=text.strip(), after=new))
                    continue
            changes.append(dict(image=stem, line=ln, action="drop_line", before=text.strip(), after="(xoá dòng)"))
        if changes:
            lp.write_text("".join(t + "\n" for t in out), encoding="utf-8")
            fixes.extend(changes)

    # 4) Ảnh chưa có nhãn: máy không bịa nhãn, chuyển người gán (không tạo file rỗng)
    seen = set()
    for i in errors:
        if i.code == "MISSING_LABEL_FILE" and i.image not in removed and i.image not in seen:
            if ds.label_path(i.image).exists():
                continue
            seen.add(i.image)
            fixes.append(dict(image=i.image, line="", action="needs_label", before="(không có file)", after="chuyển người gán"))

    return fixes
