# Báo cáo Day 09 — Đào Quang Tuấn, 2A202603194

## 1. Kết luận trước
**HOLD** (mã thoát 10). Vào 224 ảnh → cửa nhận giữ **202** → xuất `export/clean_v1` **202 ảnh** dưới dạng **bản nháp, chưa phát hành**.
Không còn lỗi bắt buộc nào (0 ERROR ở `07_error_list_v3`), nhưng **38/202 ảnh (18,8%)** còn cảnh báo chưa có người duyệt, vượt ngưỡng `warn_ratio_hold` 10%:
hàng đợi duyệt có 125 ảnh mà ngân sách chỉ 80 (`08_summary.json`).

## 2. Lỗi và phân việc
Lấy từ `02_error_list_v1`. Mẫu số: **224 ảnh** cho các lỗi ở cửa nhận, **202 ảnh** cho các lỗi nhãn (ảnh đã qua cửa nhận).

| Mã lỗi | Số dòng / ảnh | Ai sửa | Vì sao |
|---|---:|---|---|
| DUP_IMAGE_EXACT / DUP_IMAGE_NEAR | 8 / 4 ảnh (trên 224) | máy (loại ảnh) | trùng byte hoặc pHash ≤ 12: giữ 1 bản, tránh lệch phân bố |
| LEAK_TEST | 5 ảnh (trên 224) | máy (loại ảnh) | trùng ảnh test/val → nếu giữ thì điểm test bị thổi phồng |
| BAD_SIZE / CORRUPT_IMAGE | 3 / 2 ảnh (trên 224) | máy (loại ảnh) | ảnh < 250 px hoặc không `load()` được |
| BAD_CLASS_NAME | 2 dòng, 1 file `data.yaml` | máy (`rename_classes`) | quy tắc cố định: tên lớp phải đúng `cfg.classes` |
| BAD_FORMAT / BAD_CLASS_ID / BOX_ZERO / DUP_BOX | 3 / 6 / 4 / 7 dòng | máy (`drop_line`, 20 dòng) | dòng hỏng cú pháp: không thể đoán đúng ý người gán → xoá, ghi log |
| BOX_OUT_OF_IMAGE | 8 dòng / 8 ảnh | máy (`clip_box`, 8 dòng) | cắt box về [0,1], giữ nguyên lớp |
| MISSING_LABEL_FILE | 6 ảnh | **người** (`needs_label`) | máy không được bịa nhãn; file rỗng nghĩa là "ảnh nền" nên cũng không tạo |
| POSSIBLE_MISSING | 53 / 52 ảnh | **người** | model yolo26l thấy vật mà nhãn không có |
| POSSIBLE_LOOSE_BOX | 28 / 24 ảnh | **người** | đúng vật, đúng lớp nhưng IoU < 0,5 |
| POSSIBLE_FALSE_POS | 29 / 27 ảnh | **người** | box nhãn không khớp vật nào model thấy |
| POSSIBLE_WRONG_CLASS | 18 / 18 ảnh | **người** | nhầm lớp hợp lệ (chủ yếu car ↔ truck) |
| EMPTY_LABEL / BOX_TINY / BOX_HUGE / CLASS_RARE | 12 / 6 / 3 / 4 | **người** | cảnh báo: có thể đúng (ảnh nền, vật xa) hoặc sai |

Tổng cộng máy tự sửa **35 thay đổi** (`03_fixes.csv`, có cột trước → sau). `data/raw` không bị sửa: mọi thay đổi diễn ra trên bản sao `work/run/ds`.

**Hàng đợi (`05_review_queue.csv`).** Điểm ưu tiên của mỗi ảnh = Σ trọng số mã lỗi × (1 + conf của model).
`NEEDS_LABEL` nặng nhất (10), nên **6 ảnh chưa có nhãn** nằm ngay đầu hàng. Riêng `img_0020` đứng trên chúng (11,5) vì cộng dồn FIXED_DROP_LINE + MISSING + WRONG_CLASS.
Tiếp theo là các ảnh có WRONG_CLASS (trọng số 3) và MISSING (2) với conf cao. Cảnh báo cú pháp nhẹ (BOX_TINY 0,3) xếp cuối.
Với ngân sách 80/125 ảnh, người duyệt xem được **94/123 cờ ngữ nghĩa** (74/103 ảnh): 18/18 WRONG_CLASS, 51/53 MISSING, 13/24 FALSE_POS, nhưng chỉ **12/28 LOOSE_BOX**,
vì trọng số thấp (1,5) đẩy loại này xuống cuối hàng. Ảnh thấp điểm nhất vẫn được duyệt có priority 3,34.

## 3. Calibration (2 ngưỡng)
Số liệu từ `submission/calibration/calibration_report.md` (calib 39 ảnh). Mỗi ô ghi precision / recall.

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **12** | DUP_IMAGE_NEAR 1,00 / 0,50 → **1,00 / 0,67** | Lỗi này **xoá ảnh**, nên ưu tiên precision. Từ 4 đến 14 precision luôn là 1,00 và recall như nhau. Trên raw, các mức 10, 12, 14 loại đúng 4 ảnh như nhau, và cả 4 đều trùng thật khi mở xem. Chọn 12 vì nằm giữa vùng an toàn: cách cặp thật xa nhất (d = 10) và cách mức 16, nơi bắt đầu có cặp sai. |
| `second_opinion.conf` | 0,25 | **0,6** | MISSING 0,50 / 1,00 → **0,57 / 1,00**; WRONG_CLASS 0,56 / 0,83 → **0,62 / 0,83**; LOOSE_BOX 0,29 / 0,40 → 0,20 / 0,20 | Đây là cảnh báo cho người nên recall quan trọng hơn. Ở 0,6, precision tăng (người bớt mở ảnh vô ích) mà recall của MISSING và WRONG_CLASS **không giảm**. Mức 0,8 cho WRONG_CLASS precision 1,00 và kết luận đổi thành Release (7,9%), nhưng MISSING recall rơi còn 0,75 (bỏ sót 2/8). Không hạ recall chỉ để hàng đợi vừa ngân sách. Cái giá: recall LOOSE_BOX giảm, xem §4. |

**Chỗ calibration đánh lừa.** Trên calib, `phash_dist = 16` trông **tốt nhất**: DUP_IMAGE_NEAR có precision 1,00, recall 0,83, F1 0,91.
Nhưng chạy thử trên raw, mức 16 loại thêm 9 ảnh (202 → 193). Mở xem 3 cặp "gần trùng" mới thì **2/3 là ảnh khác hẳn nhau**:
`img_0011` (tennis) bị gộp với `img_0008` (trượt tuyết), `img_0177` (lướt sóng) bị gộp với `img_0113` (người ngồi bàn).
Mức 16 còn gắn thêm 6 cờ LEAK_TEST mà tôi không kiểm bằng mắt, vì không được dùng `data/test` để chọn ngưỡng.
Nguyên nhân: calib chỉ có 6 ca gần trùng, nên không có cặp ảnh khác nhau nào nằm sát ngưỡng để lộ ra FP. Precision 1,00 trên calib không có nghĩa là precision 1,00 trên raw.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
**(a) Gate chặn thật.** Chạy `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb` (không có người duyệt):
- 6 ảnh thiếu nhãn (`img_0031`, `img_0053`, `img_0126`, `img_0135`, `img_0170`, `img_0219`) vẫn còn MISSING_LABEL_FILE.
- Kết luận **REWORK**, `còn 6 lỗi bắt buộc (MISSING_LABEL_FILE=6)`, **mã thoát 20**.
- Log ghi "KHÔNG xuất: còn lỗi bắt buộc"; thư mục `work/exp_nb` **không được tạo**.

Tái lập: chạy pipeline lần 2 vào thư mục khác cho 8 file CSV, `08_summary.json` (trừ thời gian chạy) và nhãn xuất ra **giống hệt**.

**(b) Điểm mù có bằng chứng.**
1. **Model checker cũng nhầm car ↔ truck.** Sau khi người thay toàn bộ nhãn của 80 ảnh, `07_error_list_v3` vẫn còn 3 cờ WRONG_CLASS trên chính các ảnh đã duyệt:
   `img_0078`, `img_0083`, `img_0220` đều là "nhãn người ghi truck, model nói car" (conf 0,69–0,83). Vì vậy nếu nhãn raw nhầm truck → car **cùng chiều với model**, check sẽ im lặng.
   Ngoài ra còn 11 MISSING và 10 FALSE_POS trên ảnh đã có nhãn người: đây là báo động giả của model hoặc do guideline khác nhau.
2. **Box lỏng gần như lọt qua.** Recall LOOSE_BOX trên calib chỉ 0,20 (1/5). Trên raw còn 20 ảnh có cờ LOOSE_BOX sau duyệt, 16 ảnh trong số đó chưa ai xem. Box phình nhẹ (IoU vẫn ≥ 0,5) thì không bị cờ.
3. **Ảnh trùng biến đổi mạnh.** `img_0084` là bản cắt của `img_0074` (pHash = 16 > 12) nên không bị loại; calib cũng còn 2/6 ca gần trùng bị bỏ sót.

## 5. Train: raw vs clean
yolo26n, 20 epoch, imgsz 640, batch 16, seed 0 và 1, T4 Colab. Cùng val (`gold_val`, 40 ảnh) và test (100 ảnh). Bảng từ `submission/results/comparison.md`:

| biến thể | #ảnh train | số seed | mAP50 | mAP50-95 | precision | recall |
|---|---|---|---|---|---|---|
| raw | 224 | 2 | 0,726 ± 0,000 | 0,512 ± 0,004 | 0,764 ± 0,061 | 0,649 ± 0,028 |
| clean | 202 | 2 | 0,701 ± 0,025 | 0,487 ± 0,008 | 0,759 ± 0,003 | 0,625 ± 0,019 |

**Kết luận: chưa kết luận được.** Chênh mAP50 (clean − raw) là **−0,025**, bằng đúng độ lệch giữa 2 seed của clean (0,718 so với 0,683).
Độ lệch 0,000 của raw là trùng hợp: 2 seed thì không ước lượng được nhiễu.
**Không** thể nói clean tốt hơn. Cũng **không** đủ bằng chứng để nói clean kém hơn.

Giả thuyết giải thích và cách kiểm:
1. **Raw được lợi nhờ rò rỉ test.** Raw chứa 5 ảnh LEAK_TEST trùng với tập test, nên điểm raw có thể bị thổi phồng. Kiểm: train thêm biến thể "raw trừ 5 ảnh LEAK_TEST" và so lại.
2. **Clean ít dữ liệu hơn 10%.** Clean có 202 so với 224 ảnh; với lô nhỏ, mất 22 ảnh có thể nặng hơn lợi ích của việc sửa vài chục dòng nhãn. Kiểm: so learning curve, hoặc train raw trên đúng 202 ảnh đó với nhãn gốc.
3. **Lớp truck dao động mạnh.** Clean có AP50 truck 0,59 và 0,49, raw có 0,66 và 0,64; chỉ có 41 box truck. Kiểm: thêm seed và xem AP theo lớp.
4. **Clean chưa sạch hẳn.** Còn 38 ảnh có cảnh báo chưa duyệt, và box lỏng gần như không bị bắt. Kiểm: chạy biến thể `oracle` (nhãn người) làm chặn trên.

**Việc tiếp theo:** chạy ≥ 5 seed và thêm 2 biến thể (oracle, raw − LEAK) trước khi kết luận về tác dụng của pipeline lên model.

## 6. Quyết định và ghi chú AI
**(a) Quyết định: HOLD.** Để chuyển sang Release cần tỉ lệ ảnh còn cảnh báo chưa duyệt < 10%, tức ≤ 20/202 ảnh.
Cách hợp lệ là **tăng ngân sách duyệt** (duyệt thêm ít nhất 18 trong 45 ảnh còn lại của hàng đợi), hoặc cải thiện checker để giảm báo động giả.
Không đổi `warn_ratio_hold` hay ngân sách trong config: đó là quy tắc dự án.
Dataset `clean_v1` hiện chỉ dùng cho thí nghiệm, chưa phát hành.

**(b) Dùng AI:** có, Claude Code viết 4 module và soạn nháp báo cáo này; tôi đọc lại từng dòng và chịu trách nhiệm về nội dung.
- *Prompt chính:* mô tả đủ 4 ý theo `docs/PROMPTING.md`: đầu vào/đầu ra lấy từ docstring từng stub; ngưỡng phải đọc từ `cfg`; ca biên (số dòng gốc, dòng trống, dòng 2 lỗi, idempotent); không ghi vào `data/raw`.
- *Cách kiểm:*
  - `pytest` 79/79.
  - Tự thử thêm 3 ca ngoài test: dòng vừa tràn vừa trùng, dòng trống ở giữa file, ảnh `.JPG` có nhiều dự đoán.
  - Chạy pipeline 2 lần để so tái lập.
  - Mở xem bằng mắt các cặp ảnh bị coi là trùng.
- *Một lần AI sai:* khi kiểm mã thoát, AI chạy `python -m pipeline.run ... | tail; echo $?` và báo "mã thoát 0". Đó thực ra là mã thoát của `tail`. Chạy lại không qua pipe thì đúng là 10 (Hold) và 20 (Rework).

*Ghi chú kỹ thuật:* trên Windows, `check_submission.py` báo nhầm `pipeline\calibrate.py` (file đề, không sửa) có nhắc tới `MANIFEST` / `data/calib`.
Nguyên nhân: script so đường dẫn kiểu Windows (`\`) với danh sách file đề trong `_protected.json` dùng `/`. Trên Linux không có lỗi này.
4 module của tôi không bị báo.

*(Thưởng CVAT: không làm.)*
