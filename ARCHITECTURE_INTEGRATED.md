# Kiến trúc bản tích hợp

Bản này dùng `CIT-chatbot-main` làm shell (frontend, FastAPI, admin/graph API) và thay đường chạy `/chat` bằng orchestrator nhỏ.

```text
Frontend main
    -> POST /chat
    -> app/services/orchestrator.py
    -> LLM router
       |- QCHV       -> services/qchv/       (logic của Hân)
       |- CTDT       -> services/ctdt/       (logic của Linh, tách khỏi ChatService)
       |- THONG_BAO  -> services/thong_bao/  (logic Thông báo hiện tại)
       `- SOCIAL     -> LLM trực tiếp
```

## Các file chạy chính

- `backend/app/api/chat.py`: adapter request/stream cho frontend main.
- `backend/app/services/orchestrator.py`: chỉ routing và gọi đúng một pipeline.
- `backend/app/services/common/llm_service.py`: gọi Ollama + router 4 miền + normalizer Thông báo.
- `backend/app/services/qchv/quyche_service.py`: exact/vector QCHV của Hân.
- `backend/app/services/qchv/quyche_llm_service.py`: prompt QCHV của Hân.
- `backend/app/services/ctdt/query_analyzer.py`: một lần LLM phân tích truy vấn CTĐT của Linh.
- `backend/app/services/ctdt/subgraph_retriever.py`: Graph retrieval CTĐT của Linh.
- `backend/app/services/ctdt/vector_retriever.py`: vector fallback CTĐT của Linh.
- `backend/app/services/ctdt/pipeline.py`: điều phối CTĐT + prompt trả lời CTĐT.
- `backend/app/services/thong_bao/*`: pipeline retrieval Thông báo.

## Thông báo

`retriever.py` và `pipeline.py` dùng bản sửa mới hơn `backendv3(1).zip`:

1. Exact rows cùng bảng chỉ giữ representative có cosine cao nhất.
2. Representative của các bảng khác nhau tiếp tục cạnh tranh bằng cosine.
3. Candidate cùng `loai_thong_bao` được xếp thời gian mới -> cũ trước khi cắt top-k.
4. `thong_bao_khac` bị loại khỏi temporal scope.

## Những gì không còn nằm trên đường chạy chat

Không copy `chat_service.py`, `domain_service.py`, `strategy_service.py`, `retrieval_service.py` của Hân/Linh. `app/scripts/prototype.py` và service RAG cũ của main cũng được bỏ khỏi bản tích hợp vì `/chat` không còn dùng chúng.
