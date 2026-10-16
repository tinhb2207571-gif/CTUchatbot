# Bộ 35 câu hỏi–đáp án chuẩn cho miền Thông báo

Bộ dữ liệu được đối chiếu trực tiếp từ nhánh Neo4j:
`(:ThongBao)-[:CO_TAI_LIEU]->(:TaiLieu)-[:CO_MUC*1..]->(:Muc)-[:CO_BANG]->(:Bang)-[:CO_DONG]->(:DongBang)`.

## Snapshot KG cố định

- **Ngày chốt snapshot:** 16/08/2026 (Asia/Saigon).
- **Neo4j database:** `neo4j`.
- **Phạm vi:** chỉ nhánh Thông báo.
- **Số node:** 30 `ThongBao`, 44 `TaiLieu`, 110 `Muc`, 37 `Bang`, 1.529 `DongBang`.
- **Số relationship trong nhánh:** 1.720.
- **SHA-256 snapshot:** `094c504a37f9366900f2cce6bd4f5fd42efb227ce1fe3239411425cbb8fca117`.
- **Quy tắc fingerprint:** băm danh sách node/relationship đã sắp xếp; bỏ thuộc tính `embedding`, giữ ID, label, metadata và nội dung nguồn.

Hai câu có từ “mới nhất/gần nhất” được chấm theo snapshot này. Khi KG thay đổi, phải tạo
snapshot và ground truth mới; không tái sử dụng đáp án động của snapshot cũ.

## Quy ước đánh giá

- **Nhóm câu hỏi** là thách thức retrieval chính, không phải ba lớp loại trừ nhau.
- **Required facts — ALL_OF:** các fact bắt buộc để chấm `Answer Accuracy = 1`.
- **Gold evidence — ANY_OF:** 30 câu đơn node có một tập evidence chính; chỉ cần một node
  tương đương trong tập xuất hiện là đạt.
- **Multi-node — ALL_GROUPS/ANY_OF:** 5 câu tổng hợp phải phủ đủ mọi `evidence_groups`;
  trong từng group chỉ cần một node tương đương.
- **K:** lấy trực tiếp từ `top_k` truyền vào pipeline, mặc định theo
  `CHAT_GLOBAL_TOP_K` (hiện tại K = 6).

Final bundle bắt buộc gồm cả seed retrieval và candidate do Graph Expansion sinh ra:

```python
final_bundle = selected_candidates + expanded_candidates
```

Quy tắc chấm cho từng câu `q`:

```text
DirectEvidenceHit@K(q) = 1
  khi TopKSelected(q) giao GoldEvidenceAnyOf(q) khác rỗng.

FinalEvidenceHit(q) = 1
  khi FinalBundle(q) giao GoldEvidenceAnyOf(q) khác rỗng.

RecoveredByExpansion(q) = 1
  khi DirectEvidenceHit@K(q) = 0 và FinalEvidenceHit(q) = 1.

AnswerAccuracy(q) = 1
  khi câu trả lời thể hiện đủ mọi required fact của q.
```

Expansion Recovery Rate là số case recovered chia cho số case Direct Hit@K = 0. Nếu không
có Direct miss thì báo N/A. Điểm theo nhóm và toàn bộ tập là trung bình các giá trị 0/1.

## Độ đa dạng nguồn

| Thách thức retrieval chính | Số câu | Số tài liệu nguồn khác nhau |
|---|---:|---:|
| Temporal | 10 | 9 |
| Exact/Table | 10 | 7 |
| Semantic | 10 | 9 |
| Multi-node | 5 | 4 |
| Toàn bộ | 35 | 19 |

## 1. Temporal — 10 câu

### T01

- **Câu hỏi:** HK1 năm học 2026-2027 học từ ngày nào đến ngày nào?
- **Đáp án chuẩn:** Từ ngày 07/09/2026 đến ngày 20/12/2026.
- **Nguồn:** `KHGDVDKHP_HK1_26_27.pdf` (`Muc` mở đầu).
- **Required facts — ALL_OF:** `training_period_start=2026-09-07`; `training_period_end=2026-12-20`.
- **Gold evidence — ANY_OF:** `KHGDVDKHP_HK1_26_27_doc_1_muc_0`.

### T02

- **Câu hỏi:** Nếu lịch thi học phần riêng hoặc bảo vệ luận văn trùng ngày nghỉ Giỗ Tổ 07/04/2025 thì được bố trí bù khi nào?
- **Đáp án chuẩn:** Được bù vào Chủ nhật 13/04/2025, hoặc vào thời gian thích hợp khác do giảng viên sắp xếp và thông báo cho người học.
- **Nguồn:** `GioTo2025.pdf` (`Muc` duy nhất).
- **Required facts — ALL_OF:** `scheduled_makeup_date=2025-04-13`; `alternative=thời gian thích hợp do giảng viên sắp xếp và thông báo cho người học`.
- **Gold evidence — ANY_OF:** `GioTo2025_doc_1_muc_0`.

### T03

- **Câu hỏi:** Sinh viên tự đánh giá DRL HK1 2025-2026 từ ngày nào đến ngày nào?
- **Đáp án chuẩn:** Từ ngày 27/11/2025 đến ngày 07/12/2025.
- **Nguồn:** `DRL_HK1_2025_2026.pdf` (`DongBang`, dòng “SV tự đánh giá”).
- **Required facts — ALL_OF:** `self_assessment_start=2025-11-27`; `self_assessment_end=2025-12-07`.
- **Gold evidence — ANY_OF:** `DRL_HK1_2025_2026_doc_1_muc_1_bang_1_dong_3`.

### T04

- **Câu hỏi:** HK3 năm học 2025-2026 học từ ngày nào đến ngày nào?
- **Đáp án chuẩn:** Từ ngày 11/05/2026 đến ngày 23/08/2026.
- **Nguồn:** `KHGDVDKHP_HK3_25_26.pdf` (`Muc` mở đầu).
- **Required facts — ALL_OF:** `training_period_start=2026-05-11`; `training_period_end=2026-08-23`.
- **Gold evidence — ANY_OF:** `KHGDVDKHP_HK3_25_26_doc_1_muc_0`.

### T05

- **Câu hỏi:** Sinh viên tự đánh giá điểm rèn luyện học kỳ 2 năm học 2025-2026 trong khoảng thời gian nào?
- **Đáp án chuẩn:** Từ ngày 03/04/2026 đến ngày 13/04/2026.
- **Nguồn:** `DRL_HK2_2025_2026.pdf` (`DongBang`, dòng “SV tự đánh giá”).
- **Required facts — ALL_OF:** `self_assessment_start=2026-04-03`; `self_assessment_end=2026-04-13`.
- **Gold evidence — ANY_OF:** `DRL_HK2_2025_2026_doc_1_muc_1_bang_1_dong_3`.

### T06

- **Câu hỏi:** Sinh viên phản hồi kết quả đánh giá DRL HK3 2025-2026 từ ngày nào đến ngày nào?
- **Đáp án chuẩn:** Từ ngày 18/08/2026 đến ngày 31/08/2026.
- **Nguồn:** `DRL_HK3_2025_2026.pdf` (`DongBang`, dòng “Thời gian SV phản hồi”).
- **Required facts — ALL_OF:** `student_feedback_start=2026-08-18`; `student_feedback_end=2026-08-31`.
- **Gold evidence — ANY_OF:** `DRL_HK3_2025_2026_doc_1_muc_1_bang_1_dong_5`.

### T07

- **Câu hỏi:** Đại học Cần Thơ nghỉ Tết Âm lịch 2026 từ ngày nào đến ngày nào?
- **Đáp án chuẩn:** Nghỉ từ ngày 09/02/2026 đến hết Chủ nhật 22/02/2026.
- **Nguồn:** `Tet2026.pdf` (`Muc` 1, “Thời gian nghỉ Tết”).
- **Required facts — ALL_OF:** `holiday_start=2026-02-09`; `holiday_end=2026-02-22`.
- **Gold evidence — ANY_OF:** `Tet2026_doc_1_muc_1`.


### T08

- **Câu hỏi:** Đợt 2 điều chỉnh kết quả ĐKHP HK2 năm học 2025-2026 diễn ra từ ngày nào đến ngày nào?
- **Đáp án chuẩn:** Từ ngày 29/12/2025 đến ngày 04/01/2026.
- **Nguồn:** `KHGDVDKHP_HK2_25_26.pdf` (`DongBang`, dòng “SV điều chỉnh kết quả đăng ký học phần”, đợt 2).
- **Required facts — ALL_OF:** `registration_adjustment_start=2025-12-29`; `registration_adjustment_end=2026-01-04`.
- **Gold evidence — ANY_OF:** `KHGDVDKHP_HK2_25_26_doc_1_muc_0_bang_1_dong_7`.

### T09

- **Câu hỏi:** Đợt 1 ĐKHP HK1 năm học 2026-2027 diễn ra từ ngày nào đến ngày nào?
- **Đáp án chuẩn:** Từ ngày 03/08/2026 đến ngày 16/08/2026.
- **Nguồn:** `KHGDVDKHP_HK1_26_27.pdf` (`Muc` 2 của thông báo đăng ký học phần mới nhất).
- **Required facts — ALL_OF:** `round_1_start=2026-08-03`; `round_1_end=2026-08-16`.
- **Gold evidence — ANY_OF:** `KHGDVDKHP_HK1_26_27_doc_2_muc_2`; `KHGDVDKHP_HK1_26_27_doc_1_muc_0_bang_1_dong_2`.
- **Evidence audit:** `...bang_1_dong_2` chứa đầy đủ khoảng `03/8/2026 - 16/8/2026`, nên là evidence hoàn chỉnh cho cả hai required facts, không chỉ là anchor ngày bắt đầu.

### T10

- **Câu hỏi:** Đại học Cần Thơ nghỉ Quốc khánh 2026 những ngày nào, và ngày làm việc 31/08/2026 được bố trí làm bù khi nào?
- **Đáp án chuẩn:** Nghỉ ngày 01/09/2026 và 02/09/2026; ngày làm việc thứ Hai 31/08/2026 được chuyển sang làm bù vào thứ Bảy 22/08/2026, nên ngày 31/08/2026 cũng được nghỉ.
- **Nguồn:** `QuocKhanh2026.pdf` (`Muc` duy nhất).
- **Required facts — ALL_OF:** `national_day_holidays={2026-09-01,2026-09-02}`; `swapped_day_off=2026-08-31`; `makeup_workday=2026-08-22`.
- **Gold evidence — ANY_OF:** `QuocKhanh2026_doc_1_muc_0`.

## 2. Exact/Table — 10 câu

Đây là nhóm **exact/table-dominant**. Với E01–E05, exact extractor nhận mã học phần
(`CT219`, `CT182`, `CT298`, `CT112H`, `CT384`); ký hiệu lớp (`01`, `06`, `M01`)
được phân biệt tiếp bằng cosine/ranking giữa các dòng cùng mã. Vì vậy không mô tả E01–E05
là exact filter toàn bộ điều kiện.

### E01

- **Câu hỏi:** Lớp CT219-01 bị xóa ở đợt 1 HK1 2025-2026 là học phần gì?
- **Đáp án chuẩn:** Xử lý ngôn ngữ tự nhiên.
- **Nguồn:** `Xoalop_HK1_2025_2026_dot1.pdf` (`DongBang` có mã HP `CT219`, ký hiệu `01`).
- **Required facts — ALL_OF:** `course_name=Xử lý ngôn ngữ tự nhiên`.
- **Gold evidence — ANY_OF:** `Xoalop_HK1_2025_2026_dot1_doc_2_muc_0_bang_1_dong_50`.

### E02

- **Câu hỏi:** Lớp CT182-06 bị xóa ở đợt 2 HK1 năm học 2025-2026 do giảng viên nào phụ trách?
- **Đáp án chuẩn:** Phạm Thị Xuân Lộc (mã số CBGD 700556).
- **Nguồn:** `Xoalop_HK1_2025_2026_dot2.pdf` (`DongBang` có mã HP `CT182`, ký hiệu `06`).
- **Required facts — ALL_OF:** `lecturer_name=Phạm Thị Xuân Lộc`; `lecturer_id=700556`.
- **Gold evidence — ANY_OF:** `Xoalop_HK1_2025_2026_dot2_doc_2_muc_0_bang_1_dong_3`.

### E03

- **Câu hỏi:** Lớp CT298-01 bị xóa trong HK2 2025-2026 có bao nhiêu tín chỉ và do ai giảng dạy?
- **Đáp án chuẩn:** 3 tín chỉ; giảng viên Trần Nguyễn Minh Thái (mã số CBGD 02226).
- **Nguồn:** `Xoalop_HK2_2025_2026.pdf` (`DongBang` có mã HP `CT298`, ký hiệu `01`).
- **Required facts — ALL_OF:** `credits=3`; `lecturer_name=Trần Nguyễn Minh Thái`; `lecturer_id=02226`.
- **Gold evidence — ANY_OF:** `Xoalop_HK2_2025_2026_doc_2_muc_0_bang_1_dong_10`.

### E04

- **Câu hỏi:** Lớp CT112H-M01 bị xóa trong HK3 năm học 2025-2026 là học phần nào?
- **Đáp án chuẩn:** Phân tích và thiết kế hệ thống.
- **Nguồn:** `Xoalop_HK3_2025_2026.pdf` (`DongBang` có mã HP `CT112H`, ký hiệu `M01`).
- **Required facts — ALL_OF:** `course_name=Phân tích và thiết kế hệ thống`.
- **Gold evidence — ANY_OF:** `Xoalop_HK3_2025_2026_doc_2_muc_0_bang_1_dong_3`.

### E05

- **Câu hỏi:** Trong danh sách xóa lớp đợt 2 HK2 2024-2025, CT384-01 là học phần gì và có bao nhiêu tín chỉ?
- **Đáp án chuẩn:** Mạng nơ-ron nhân tạo, 3 tín chỉ.
- **Nguồn:** `Xoalop_HK2_2024_2025_dot2.pdf` (`DongBang` có mã HP `CT384`, ký hiệu `01`).
- **Required facts — ALL_OF:** `course_name=Mạng nơ-ron nhân tạo`; `credits=3`.
- **Gold evidence — ANY_OF:** `Xoalop_HK2_2024_2025_dot2_doc_2_muc_0_bang_1_dong_2`.

### E06

- **Câu hỏi:** MSSV B2400695 được chuyển từ lớp nào sang lớp nào, sang ngành gì và thuộc đơn vị nào?
- **Đáp án chuẩn:** Sinh viên Phan Thị Kim Hận, MSSV B2400695, chuyển từ lớp TS2413A2 sang lớp TS2482A1, ngành Công nghệ Chế biến thủy sản, thuộc Trường Thuỷ sản.
- **Nguồn:** `ChuyenNganh10_2025.signed.signed.pdf` (`DongBang` có Mã SV `B2400695`).
- **Required facts — ALL_OF:** `student_name=Phan Thị Kim Hận`; `student_id=B2400695`; `old_class=TS2413A2`; `new_class=TS2482A1`; `new_major=Công nghệ Chế biến thủy sản`; `new_unit=Trường Thuỷ sản`.
- **Gold evidence — ANY_OF:** `ChuyenNganh10_2025.signed.signed_doc_2_muc_0_bang_1_dong_61`.

### E07

- **Câu hỏi:** MSSV B2405750 được chuyển từ lớp nào sang lớp nào, sang ngành gì và thuộc đơn vị nào?
- **Đáp án chuẩn:** Chuyển từ lớp TN24D5A1 sang lớp TN2484A1, ngành Kỹ thuật cơ khí (Chuyên ngành Cơ khí chế tạo máy), thuộc Trường Bách khoa.
- **Nguồn:** `ChuyenNganh10_2025.signed.signed.pdf` (`DongBang` có Mã SV `B2405750`).
- **Required facts — ALL_OF:** `old_class=TN24D5A1`; `new_class=TN2484A1`; `new_major=Kỹ thuật cơ khí (Chuyên ngành Cơ khí chế tạo máy)`; `new_unit=Trường Bách khoa`.
- **Gold evidence — ANY_OF:** `ChuyenNganh10_2025.signed.signed_doc_2_muc_0_bang_1_dong_20`.

### E08

- **Câu hỏi:** MSSV B2404384 được chuyển đến lớp nào, ngành gì và thuộc đơn vị nào?
- **Đáp án chuẩn:** Chuyển đến lớp DA2408A3, ngành Công nghệ Thực phẩm, thuộc Viện Công Nghệ Sinh học và Thực phẩm.
- **Nguồn:** `ChuyenNganh10_2025.signed.signed.pdf` (`DongBang` có Mã SV `B2404384`).
- **Required facts — ALL_OF:** `new_class=DA2408A3`; `new_major=Công nghệ Thực phẩm`; `new_unit=Viện Công Nghệ Sinh học và Thực phẩm`.
- **Gold evidence — ANY_OF:** `ChuyenNganh10_2025.signed.signed_doc_2_muc_0_bang_1_dong_69`.

### E09

- **Câu hỏi:** K50 thuộc Nhóm đơn vị 6 bắt đầu ĐKHP đợt 1 lúc mấy giờ, ngày nào?
- **Đáp án chuẩn:** Lúc 13:30 ngày 05/08/2026.
- **Nguồn:** `KHGDVDKHP_HK1_26_27.pdf` (`DongBang` trong bảng lịch đăng ký đợt 1).
- **Required facts — ALL_OF:** `registration_time=13:30`; `registration_date=2026-08-05`.
- **Gold evidence — ANY_OF:** `KHGDVDKHP_HK1_26_27_doc_2_muc_2_bang_1_dong_16`.
- **Retrieval note:** Đây là case hybrid: `Khóa 50` được lọc exact; điều kiện `Nhóm đơn vị 6` phải được phân biệt bằng cosine/ranking giữa các dòng cùng khóa.

### E10

- **Câu hỏi:** Ở đợt 2 đăng ký học phần học kỳ 1 năm học 2026-2027, Khóa 51 thuộc Nhóm đơn vị 2 hoặc 4 bắt đầu đăng ký lúc nào?
- **Đáp án chuẩn:** Lúc 13:30 ngày 09/09/2026.
- **Nguồn:** `KHGDVDKHP_HK1_26_27.pdf` (`DongBang` trong bảng lịch đăng ký đợt 2).
- **Required facts — ALL_OF:** `registration_time=13:30`; `registration_date=2026-09-09`.
- **Gold evidence — ANY_OF:** `KHGDVDKHP_HK1_26_27_doc_2_muc_2_bang_2_dong_11`.
- **Retrieval note:** Đây là case hybrid: `Khóa 51` được lọc exact; điều kiện `Nhóm đơn vị 2 hoặc 4` phải được phân biệt bằng cosine/ranking giữa các dòng cùng khóa.

## 3. Semantic — 10 câu

### S01

- **Câu hỏi:** Nếu lớp đã đăng ký bị xóa sau đợt 1 của học kỳ 1 năm học 2025-2026, sinh viên có những phương án xử lý nào?
- **Đáp án chuẩn:** Sinh viên có thể chuyển kế hoạch học tập sang học kỳ tiếp theo, đăng ký vào lớp học phần còn lại, hoặc đăng ký học phần khác thay thế trong đợt 2 từ 08/09/2025 đến 14/09/2025.
- **Nguồn:** `Xoalop_HK1_2025_2026_dot1.pdf` (`Muc` thông báo).
- **Required facts — ALL_OF:** `option_1=chuyển kế hoạch học tập sang học kỳ tiếp theo`; `option_2=đăng ký lớp học phần còn lại`; `option_3=đăng ký học phần khác thay thế`; `round_2_period=2025-09-08..2025-09-14`.
- **Gold evidence — ANY_OF:** `Xoalop_HK1_2025_2026_dot1_doc_1_muc_0`.

### S02

- **Câu hỏi:** Sau khi lớp bị xóa ở đợt đăng ký cuối của học kỳ 2 năm học 2025-2026, sinh viên muốn đổi sang lớp khác thì phải làm gì?
- **Đáp án chuẩn:** Sinh viên phải liên hệ Phòng Đào tạo qua email `nhdnhan@ctu.edu.vn` để được hỗ trợ, chậm nhất đến hết ngày 08/01/2026. Sau thời hạn này, Trường sẽ chính thức xóa kết quả đăng ký.
- **Nguồn:** `Xoalop_HK2_2025_2026.pdf` (`Muc` thông báo).
- **Required facts — ALL_OF:** `contact_unit=Phòng Đào tạo`; `contact_email=nhdnhan@ctu.edu.vn`; `deadline=2026-01-08`; `after_deadline=Trường xóa kết quả đăng ký`.
- **Gold evidence — ANY_OF:** `Xoalop_HK2_2025_2026_doc_1_muc_0`.

### S03

- **Câu hỏi:** Sinh viên chưa nhập kế hoạch học tập học kỳ 1 năm học 2026-2027 có được bổ sung vào một lớp đã đủ sĩ số không?
- **Đáp án chuẩn:** Không. Sinh viên được điều chỉnh kế hoạch và đăng ký trong thời gian quy định, nhưng nếu lớp học phần đã hết chỗ thì sẽ không được xem xét bổ sung.
- **Nguồn:** `KHGDVDKHP_HK1_26_27.pdf` (`Muc` 1).
- **Required facts — ALL_OF:** `supplement_when_class_full=false`; `reason=lớp học phần đã hết chỗ`.
- **Gold evidence — ANY_OF:** `KHGDVDKHP_HK1_26_27_doc_1_muc_1`.

### S04

- **Câu hỏi:** Trong HK1 2025-2026, sinh viên có thể đăng ký học phần bằng điện thoại hay phải dùng máy tính?
- **Đáp án chuẩn:** Sinh viên có thể đăng ký bằng điện thoại thông minh cá nhân qua ứng dụng MyCTUS, bằng máy tính cá nhân hoặc máy tính tại Trung tâm học liệu Trường.
- **Nguồn:** `KHGDVDKHP_HK1_25_26.pdf` (`Muc` 4 của tài liệu phân chia kế hoạch đăng ký).
- **Required facts — ALL_OF:** `registration_device_1=điện thoại thông minh cá nhân qua ứng dụng MyCTUS`; `registration_device_2=máy tính cá nhân`; `registration_device_3=máy tính tại Trung tâm học liệu Trường`.
- **Gold evidence — ANY_OF:** `KHGDVDKHP_HK1_25_26_doc_2_muc_4`.

### S05

- **Câu hỏi:** Thư viện Đại học Cần Thơ hỗ trợ sinh viên đăng ký học phần trực tuyến như thế nào?
- **Đáp án chuẩn:** Thư viện Đại học Cần Thơ cử cán bộ trực và mở cửa phòng máy phục vụ sinh viên đăng ký theo thời gian đã công bố.
- **Nguồn:** `KHGDVDKHP_HK1_26_27.pdf` (`Muc` 5 của tài liệu phân chia kế hoạch đăng ký).
- **Required facts — ALL_OF:** `staffing=cử cán bộ trực`; `facility=mở cửa phòng máy phục vụ sinh viên đăng ký`; `availability=theo thời gian đăng ký đã công bố`.
- **Gold evidence — ANY_OF:** `KHGDVDKHP_HK1_26_27_doc_2_muc_5`.

### S06

- **Câu hỏi:** Hướng dẫn quy trình đánh giá DRL HK3 2024-2025 trực tuyến được đăng ở đâu?
- **Đáp án chuẩn:** Xem trên website Phòng Công tác Sinh viên tại https://dsa.ctu.edu.vn/images/upload/vbanply/2018/DRL/quytrinh_DRL_tructuyen.pdf.
- **Nguồn:** `DRL_HK3_2024_2025.pdf` (`Muc` 2, quy trình thực hiện đánh giá).
- **Required facts — ALL_OF:** `online_guide_url=https://dsa.ctu.edu.vn/images/upload/vbanply/2018/DRL/quytrinh_DRL_tructuyen.pdf`.
- **Gold evidence — ANY_OF:** `DRL_HK3_2024_2025_doc_1_muc_2`.

### S07

- **Câu hỏi:** Nếu học phần sinh viên cần chưa được mở trong HK3 2025-2026, Nhà trường có mở lớp theo yêu cầu sinh viên không và hạn cuối là khi nào?
- **Đáp án chuẩn:** Có. Phòng Đào tạo phối hợp với đơn vị mở lớp học phần mới theo yêu cầu sinh viên, hạn cuối là ngày 17/04/2026.
- **Nguồn:** `KHGDVDKHP_HK3_25_26.pdf` (`DongBang`, dòng mở lớp HP mới theo yêu cầu SV).
- **Required facts — ALL_OF:** `new_class_support=PĐT phối hợp với đơn vị mở lớp HP mới theo yêu cầu SV`; `deadline=2026-04-17`.
- **Gold evidence — ANY_OF:** `KHGDVDKHP_HK3_25_26_doc_1_muc_0_bang_1_dong_4`.

### S08

- **Câu hỏi:** Trong kỳ nghỉ Tết 2025, nếu gặp vấn đề ở ký túc xá thì sinh viên liên hệ số nào?
- **Đáp án chuẩn:** Liên hệ Ký túc xá (Phòng Công tác Sinh viên) qua số (0292) 3872275.
- **Nguồn:** `Tet2025.pdf` (`Muc` 3, các số liên hệ trong thời gian nghỉ Tết).
- **Required facts — ALL_OF:** `contact_unit=Ký túc xá (PCTSV)`; `contact_phone=(0292) 3872275`.
- **Gold evidence — ANY_OF:** `Tet2025_doc_1_muc_3`.

### S09

- **Câu hỏi:** Quyền lợi và chế độ của sinh viên thay đổi thế nào sau khi được chấp thuận chuyển ngành tháng 10/2025?
- **Đáp án chuẩn:** Mọi chế độ và quyền lợi của sinh viên tiếp tục được thực hiện khi chuyển sang lớp học mới.
- **Nguồn:** `ChuyenNganh10_2025.signed.signed.pdf` (`Muc` Điều 2).
- **Required facts — ALL_OF:** `student_benefits=tiếp tục được thực hiện khi chuyển sang lớp học mới`.
- **Gold evidence — ANY_OF:** `ChuyenNganh10_2025.signed.signed_doc_1_muc_điều_2`.

### S10

- **Câu hỏi:** Các buổi dạy và học trùng kỳ nghỉ Quốc khánh 2025 được bố trí bù như thế nào?
- **Đáp án chuẩn:** Được bố trí bù vào tuần dự trữ của học kỳ với tiết học và phòng học không thay đổi, hoặc vào thời gian phù hợp do giảng viên sắp xếp và thống nhất với người học.
- **Nguồn:** `QuocKhanh2025.pdf` (`Muc` duy nhất).
- **Required facts — ALL_OF:** `option_1=tuần dự trữ với tiết học và phòng học không thay đổi`; `option_2=thời gian phù hợp do giảng viên sắp xếp và thống nhất với người học`.
- **Gold evidence — ANY_OF:** `QuocKhanh2025_doc_1_muc_0`.

## 4. Multi-node — 5 câu

Các case này chỉ đạt `Final Evidence Hit = 1` khi bundle chứa ít nhất một node thuộc mọi
group bắt buộc. Các group độc lập dùng quan hệ `ALL_GROUPS`; node trong một group dùng
quan hệ `ANY_OF`.

### MN01

- **Câu hỏi:** Đại học Cần Thơ nghỉ Tết Âm lịch 2026 từ ngày nào đến ngày nào và sinh viên bắt đầu học lại khi nào?
- **Đáp án chuẩn:** Đại học Cần Thơ nghỉ từ ngày 09/02/2026 đến hết Chủ nhật 22/02/2026. Sinh viên bắt đầu học lại từ thứ Hai 23/02/2026.
- **Nguồn:** `Tet2026.pdf` (`Muc` 1 và `Muc` 2).
- **Required facts — ALL_OF:** `holiday_start=2026-02-09`; `holiday_end=2026-02-22`; `teaching_resume=2026-02-23`.
- **Evidence groups — ALL_GROUPS:** `holiday_period` → `Tet2026_doc_1_muc_1`; `teaching_resume` → `Tet2026_doc_1_muc_2`.

### MN02

- **Câu hỏi:** Nếu không có thiết bị cá nhân để ĐKHP trực tuyến HK1 năm học 2026-2027, sinh viên có thể đăng ký ở đâu và được Thư viện hỗ trợ như thế nào?
- **Đáp án chuẩn:** Sinh viên có thể dùng máy tính tại Thư viện Đại học Cần Thơ. Thư viện cử cán bộ trực và mở cửa phòng máy phục vụ sinh viên đăng ký theo thời gian đã công bố.
- **Nguồn:** `KHGDVDKHP_HK1_26_27.pdf` (`Muc` 4 và `Muc` 5).
- **Required facts — ALL_OF:** `available_equipment=máy tính tại Thư viện Đại học Cần Thơ`; `staffing=cử cán bộ trực`; `facility=mở cửa phòng máy phục vụ sinh viên đăng ký`; `availability=theo thời gian đăng ký đã công bố`.
- **Evidence groups — ALL_GROUPS:** `available_equipment` → `KHGDVDKHP_HK1_26_27_doc_2_muc_4`; `library_support` → `KHGDVDKHP_HK1_26_27_doc_2_muc_5`.

### MN03

- **Câu hỏi:** Sinh viên K50 của Trường Công nghệ Thông tin và Truyền thông hoặc Trường Thủy sản bắt đầu ĐKHP đợt 1 HK1 năm học 2026-2027 lúc nào?
- **Đáp án chuẩn:** Hai trường thuộc Nhóm đơn vị 6, nên sinh viên K50 bắt đầu đăng ký lúc 13:30 ngày 05/08/2026.
- **Nguồn:** `KHGDVDKHP_HK1_26_27.pdf` (`Muc` 1 và dòng 16 của bảng lịch đợt 1).
- **Required facts — ALL_OF:** `unit_group=6`; `group_members={Trường Công nghệ Thông tin và Truyền thông,Trường Thủy sản}`; `registration_time=13:30`; `registration_date=2026-08-05`.
- **Evidence groups — ALL_GROUPS:** `unit_group_mapping` → `KHGDVDKHP_HK1_26_27_doc_2_muc_1`; `registration_schedule` → `KHGDVDKHP_HK1_26_27_doc_2_muc_2_bang_1_dong_16`.

### MN04

- **Câu hỏi:** Lớp CT219-01 bị xóa sau đợt 1 HK1 năm học 2025-2026 là học phần nào và sinh viên đã đăng ký lớp này có những phương án xử lý nào?
- **Đáp án chuẩn:** CT219-01 là học phần Xử lý ngôn ngữ tự nhiên. Sinh viên có thể chuyển kế hoạch học tập sang học kỳ tiếp theo, đăng ký lớp học phần còn lại hoặc đăng ký học phần khác thay thế trong đợt 2 từ 08/09/2025 đến 14/09/2025.
- **Nguồn:** `Xoalop_HK1_2025_2026_dot1.pdf` (dòng lớp CT219-01 và `Muc` chính sách xử lý).
- **Required facts — ALL_OF:** `course_name=Xử lý ngôn ngữ tự nhiên`; `option_1=chuyển kế hoạch học tập sang học kỳ tiếp theo`; `option_2=đăng ký lớp học phần còn lại`; `option_3=đăng ký học phần khác thay thế`; `round_2_period=2025-09-08..2025-09-14`.
- **Evidence groups — ALL_GROUPS:** `deleted_course_row` → `Xoalop_HK1_2025_2026_dot1_doc_2_muc_0_bang_1_dong_50`; `student_handling_policy` → `Xoalop_HK1_2025_2026_dot1_doc_1_muc_0`.

### MN05

- **Câu hỏi:** MSSV B2405750 được chuyển sang lớp và ngành nào, việc chuyển ngành áp dụng từ học kỳ nào và quyền lợi sau khi chuyển được giải quyết ra sao?
- **Đáp án chuẩn:** Sinh viên Trương Khải Văn, MSSV B2405750, được chuyển sang lớp TN2484A1, ngành Kỹ thuật cơ khí (Chuyên ngành Cơ khí chế tạo máy), thuộc Trường Bách khoa. Việc chuyển ngành áp dụng từ HK2 năm học 2025-2026; mọi chế độ và quyền lợi tiếp tục được thực hiện khi chuyển sang lớp học mới.
- **Nguồn:** `ChuyenNganh10_2025.signed.signed.pdf` (dòng sinh viên 20, Điều 1 và Điều 2).
- **Required facts — ALL_OF:** `student_name=Trương Khải Văn`; `student_id=B2405750`; `new_class=TN2484A1`; `new_major=Kỹ thuật cơ khí (Chuyên ngành Cơ khí chế tạo máy)`; `new_unit=Trường Bách khoa`; `effective_semester=HK2 2025-2026`; `student_benefits=tiếp tục được thực hiện khi chuyển sang lớp học mới`.
- **Evidence groups — ALL_GROUPS:** `student_transfer_row` → `ChuyenNganh10_2025.signed.signed_doc_2_muc_0_bang_1_dong_20`; `effective_semester` → `ChuyenNganh10_2025.signed.signed_doc_1_muc_điều_1`; `benefits_policy` → `ChuyenNganh10_2025.signed.signed_doc_1_muc_điều_2`.
