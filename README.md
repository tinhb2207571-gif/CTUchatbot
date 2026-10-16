# CTU Chatbot

Chatbot tư vấn Đại học Cần Thơ dùng Next.js, FastAPI, Neo4j và Ollama.

## Chạy ứng dụng

Xem [hướng dẫn Windows](RUN_WINDOWS.md) để cài thư viện, cấu hình Neo4j/Ollama và chạy backend, frontend.

- Giao diện: http://localhost:3000
- Quản trị tài liệu PDF: http://localhost:3000/admin
- API: http://localhost:8000/docs
- Tài khoản quản trị mặc định cho chạy thử local: `admin` / `123456`.

Tạo `backend/.env` từ `backend/.env.example` và điền thông tin kết nối của bạn.
`LLM_MODEL` chọn mô hình dùng chung cho các luồng chat; embedding có cấu hình riêng.
Không đưa `.env` có mật khẩu lên GitHub. Tài khoản demo và khóa JWT trong source cần thay trước khi triển khai công khai.

## Chức năng

- Chat theo ba miền: Chương trình đào tạo, Quy chế học vụ, Thông báo.
- Trả lời từng phần từ Ollama lên giao diện.
- Upload PDF từ trang admin, xử lý và nhập Neo4j theo từng miền.
- Thông báo: sáu bước xử lý PDF, nhập từng cây tài liệu và embedding trong transaction.
- Hướng dẫn thủ tục hiện chỉ lưu file, chưa có bộ xử lý nhập graph.

## Source

- `frontend/`: giao diện Next.js và proxy API chat.
- `backend/app/api/`: API chat, đăng nhập, upload và trạng thái xử lý.
- `backend/app/services/`: điều phối, truy xuất và sinh câu trả lời.
- `backend/app/scripts/`: xử lý PDF và nhập graph.
- `backend/tests/`, `frontend/tests/`: kiểm thử.

Model, thư viện đã cài, file upload và dữ liệu sinh ra được bỏ qua bởi Git.
Máy mới cần tải model và nhập tài liệu vào Neo4j để trả lời câu hỏi theo tài liệu.

## Kiểm thử

Từ thư mục `backend`:

```powershell
..\.venv\Scripts\python.exe -X utf8 -m pytest tests -q
```

Từ thư mục `frontend`:

```powershell
node --test tests/chat-stream.test.mjs
npx.cmd tsc --noEmit --incremental false
```
