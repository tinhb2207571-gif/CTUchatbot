# Chạy trên Windows

## 1. Chuẩn bị
- Neo4j đang chạy và database đã có KG/index cần thiết.
- Ollama đang chạy và có model `qwen3.5:9b`.
- Node.js/npm đã cài.
- Python đã cài.

## 2. Backend
Mở PowerShell tại thư mục project:

```powershell
cd backend
py -3.10 -m venv ..\.venv
..\.venv\Scripts\python.exe -m pip install --upgrade pip
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Sửa tối thiểu trong `.env`:

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=MAT_KHAU_NEO4J_CUA_BAN
NEO4J_DATABASE=neo4j
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL=qwen3.5:9b
EMBEDDING_DEVICE=cpu
```

Nếu có BGE-M3 local, có thể thêm:

```env
EMBEDDING_MODEL_PATH=C:/duong/dan/toi/bge-m3
```

Nếu không khai báo `EMBEDDING_MODEL_PATH`, lần retrieval đầu sẽ dùng `BAAI/bge-m3` qua Hugging Face và cache model.

Chạy backend:

```powershell
..\.venv\Scripts\python.exe -X utf8 -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Kiểm tra: mở `http://127.0.0.1:8000/`, phải thấy `{"msg":"API running"}`.

## 3. Ollama
Trong terminal khác:

```powershell
ollama list
```

Nếu chưa có `qwen3.5:9b`:

```powershell
ollama pull qwen3.5:9b
```

Nếu Ollama chưa chạy, mở ứng dụng Ollama hoặc chạy `ollama serve`.

## 4. Frontend
Mở terminal mới tại project:

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

Mở `http://localhost:3000`.

Frontend proxy chat đến `http://127.0.0.1:8000/chat`.
