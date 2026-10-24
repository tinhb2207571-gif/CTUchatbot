import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.services.common import llm_service
from app.services.ctdt import query_analyzer


class LLMDiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    async def call_json(self, handler):
        real_client = httpx.AsyncClient
        with patch.object(llm_service.httpx, "AsyncClient", side_effect=lambda **kw: real_client(
            transport=httpx.MockTransport(handler), **kw
        )):
            return await llm_service.call_model_json("test-model", "private prompt")

    async def test_empty_answer_logs_length_reason_and_thinking_size(self):
        payload = {"response": "", "thinking": "hidden reasoning", "done": True,
                   "done_reason": "length", "eval_count": 4096, "prompt_eval_count": 500}
        with self.assertLogs("app.llm", level="WARNING") as logs:
            self.assertEqual(await self.call_json(lambda r: httpx.Response(200, json=payload)), {})
        text = "\n".join(logs.output)
        self.assertIn('"done_reason": "length"', text)
        self.assertIn('"eval_count": 4096', text)
        self.assertIn('"thinking_chars": 16', text)
        self.assertIn('"reason": "empty_response"', text)
        self.assertNotIn("hidden reasoning", text)
        self.assertNotIn("private prompt", text)

    async def test_chat_fallback_logs_its_own_completion_metadata(self):
        def handler(request):
            if request.url.path.endswith("generate"):
                return httpx.Response(404)
            return httpx.Response(200, json={"message": {"content": '{"ok":true}'},
                                            "done": True, "done_reason": "stop", "eval_count": 6})
        with self.assertLogs("app.llm", level="INFO") as logs:
            self.assertEqual(await self.call_json(handler), {"ok": True})
        self.assertIn('"endpoint": "chat"', logs.output[0])
        self.assertIn('"done_reason": "stop"', logs.output[0])
        self.assertFalse(any("WARNING" in line for line in logs.output))

    async def test_invalid_json_preview_is_bounded_and_return_unchanged(self):
        content = "không phải JSON " * 300
        with self.assertLogs("app.llm", level="WARNING") as logs:
            result = await self.call_json(lambda r: httpx.Response(200, json={"response": content}))
        self.assertEqual(result, {})
        warning = json.loads(logs.output[0].split("[LLM][JSON_WARNING] ")[1])
        self.assertEqual(len(warning["response_preview"]), 2000)
        self.assertTrue(warning["preview_truncated"])

    async def test_missing_metadata_does_not_invent_stop_reason(self):
        with self.assertLogs("app.llm", level="INFO") as logs:
            self.assertEqual(await self.call_json(lambda r: httpx.Response(200, json={"response": '{"ok":true}'})), {"ok": True})
        self.assertIn('"done_reason": null', logs.output[0])

    async def test_empty_analysis_warns_and_keeps_existing_defaults(self):
        with patch.object(query_analyzer, "call_model_json", new_callable=AsyncMock, return_value={}):
            with self.assertLogs("app.ctdt.analysis", level="WARNING") as logs:
                result = await query_analyzer.analyze_ctdt_query("Tổng tín chỉ KHMT?")
        self.assertEqual(result["entities"], [])
        self.assertEqual(result["rewrite"], "Tổng tín chỉ KHMT?")
        self.assertIn("reason=empty_analysis", logs.output[0])

    async def test_valid_json_without_entities_is_flagged_for_ctdt(self):
        with patch.object(query_analyzer, "call_model_json", new_callable=AsyncMock,
                          return_value={"entities": [], "query_type": "description"}):
            with self.assertLogs("app.ctdt.analysis", level="WARNING") as logs:
                await query_analyzer.analyze_ctdt_query("Tổng tín chỉ KHMT?")
        self.assertIn("reason=no_entities", logs.output[0])
