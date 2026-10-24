import asyncio
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx

from app.services.common import embedding_cache
from app.services.common.streaming import answer_token_handler, stream_ollama_answer


class EmbeddingCacheTests(unittest.TestCase):
    def test_parallel_requests_load_model_only_once(self):
        constructor = Mock(return_value=object())
        with patch.object(embedding_cache, "_models", {}), patch.dict(
            "sys.modules", {"sentence_transformers": SimpleNamespace(SentenceTransformer=constructor)}
        ):
            with ThreadPoolExecutor(max_workers=4) as pool:
                models = list(pool.map(lambda _: embedding_cache.get_sentence_transformer("test", "cpu"), range(8)))
            self.assertTrue(all(model is models[0] for model in models))
            constructor.assert_called_once()


class OllamaStreamingTests(unittest.IsolatedAsyncioTestCase):
    async def test_json_analysis_does_not_stream_to_user(self):
        from unittest.mock import AsyncMock
        from app.services.common import llm_service
        tokens = []
        token = answer_token_handler.set(tokens.append)
        try:
            with patch.object(llm_service, "call_model", new_callable=AsyncMock, return_value='{"ok": true}') as call:
                result = await llm_service.call_model_json("test", "analyze")
        finally:
            answer_token_handler.reset(token)
        self.assertEqual(result, {"ok": True})
        self.assertEqual(tokens, [])
        self.assertTrue(call.call_args.kwargs["think"])
        self.assertEqual(call.call_args.kwargs["num_predict"], 4096)

    async def run_stream(self, handler):
        real_client = httpx.AsyncClient
        transport = httpx.MockTransport(handler)
        tokens = []
        token = answer_token_handler.set(tokens.append)
        try:
            with patch("app.services.common.streaming.httpx.AsyncClient", side_effect=lambda **kwargs: real_client(transport=transport, **kwargs)):
                answer = await stream_ollama_answer(
                    "test", "question", generate_url="http://test/generate", chat_url="http://test/chat",
                    timeout=1, temperature=0.2, num_predict=256,
                )
        finally:
            answer_token_handler.reset(token)
        return answer, tokens

    async def test_tokens_keep_vietnamese_and_ignore_thinking(self):
        def handler(request):
            payload = json.loads(request.content)
            self.assertTrue(payload["stream"])
            self.assertTrue(payload["think"])
            return httpx.Response(200, text='{"thinking":"hidden","response":"Xin "}\n{"response":"chào","done":true}\n')
        answer, tokens = await self.run_stream(handler)
        self.assertEqual(tokens, ["Xin ", "chào"])
        self.assertEqual(answer, "Xin chào")

    async def test_generate_404_falls_back_to_chat(self):
        calls = []
        def handler(request):
            calls.append(request.url.path)
            if request.url.path == "/generate":
                return httpx.Response(404)
            self.assertIn("messages", json.loads(request.content))
            return httpx.Response(200, text='{"message":{"content":"ok"},"done":true}\n')
        self.assertEqual(await self.run_stream(handler), ("ok", ["ok"]))
        self.assertEqual(calls, ["/generate", "/chat"])

    async def test_interrupted_stream_is_an_error(self):
        with self.assertRaisesRegex(RuntimeError, "hoàn tất"):
            await self.run_stream(lambda request: httpx.Response(200, text='{"response":"partial"}\n'))

    async def test_http_error_does_not_fall_back(self):
        with self.assertRaises(httpx.HTTPStatusError):
            await self.run_stream(lambda request: httpx.Response(500))


class ChatEndpointStreamingTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_token_arrives_before_answer_finishes(self):
        from app.api.chat import chat, ChatRequest, chat_orchestrator
        release = asyncio.Event()

        async def generate(*args):
            answer_token_handler.get()("Đầu ")
            await release.wait()
            answer_token_handler.get()("cuối")
            return {"answer": "Đầu cuối"}

        with patch.object(chat_orchestrator, "handle_query", side_effect=generate):
            response = await chat(ChatRequest(message="test"))
            first = await asyncio.wait_for(response.body_iterator.__anext__(), 2)
            self.assertEqual(json.loads(first[2:]), "Đầu ")
            release.set()
            rest = [part async for part in response.body_iterator]
        self.assertEqual([json.loads(part[2:]) for part in rest], ["cuối"])
        self.assertIsNone(answer_token_handler.get())

    async def test_error_frame_follows_partial_answer(self):
        from app.api.chat import chat, ChatRequest, chat_orchestrator
        async def generate(*args):
            answer_token_handler.get()("partial")
            raise RuntimeError("test failure")
        with patch.object(chat_orchestrator, "handle_query", side_effect=generate):
            response = await chat(ChatRequest(message="test"))
            parts = [part async for part in response.body_iterator]
        self.assertTrue(parts[0].startswith("0:"))
        self.assertTrue(parts[1].startswith("3:"))

    async def test_closing_stream_cancels_generation(self):
        from app.api.chat import chat, ChatRequest, chat_orchestrator
        cancelled = asyncio.Event()
        async def generate(*args):
            try:
                answer_token_handler.get()("first")
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        with patch.object(chat_orchestrator, "handle_query", side_effect=generate):
            response = await chat(ChatRequest(message="test"))
            await response.body_iterator.__anext__()
            await response.body_iterator.aclose()
        self.assertTrue(cancelled.is_set())


class QuyCheStreamingTests(unittest.TestCase):
    def test_only_final_answer_streams(self):
        from app.services.qchv.quyche_llm_service import QuyCheLLMService
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.iter_lines.return_value = [
            json.dumps({"message": {"content": "Xin "}}).encode(),
            json.dumps({"message": {"content": "chào"}, "done": True}).encode(),
        ]
        tokens = []
        token = answer_token_handler.set(tokens.append)
        try:
            with patch("app.services.qchv.quyche_llm_service.requests.post", return_value=response) as post:
                answer = QuyCheLLMService().generate_answer("test", "context", [])
        finally:
            answer_token_handler.reset(token)
        self.assertEqual(answer, "Xin chào")
        self.assertEqual(tokens, ["Xin ", "chào"])
        self.assertTrue(post.call_args.kwargs["stream"])
        self.assertTrue(post.call_args.kwargs["json"]["think"])
