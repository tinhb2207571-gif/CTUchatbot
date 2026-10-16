import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from app.services.common import llm_service
from app.services.qchv import quyche_llm_service


class SharedModelTests(unittest.TestCase):
    def test_one_environment_value_controls_all_domains(self):
        environment = dict(os.environ, LLM_MODEL="test-shared-model")
        # Các override cũ không còn chia mô hình theo từng tác vụ.
        environment.update(ROUTER_MODEL="old-router", NOTIFICATION_NORMALIZER_MODEL="old-notice")
        code = """
from app.core.llm_config import LLM_MODEL
from app.services.common import llm_service
from app.services.ctdt import query_analyzer
from app.services.qchv.quyche_llm_service import QuyCheLLMService
assert LLM_MODEL == 'test-shared-model'
assert llm_service.LLM_MODEL == LLM_MODEL
assert query_analyzer.LLM_MODEL == LLM_MODEL
assert QuyCheLLMService().model_primary == LLM_MODEL
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=Path(__file__).resolve().parents[1],
            env=environment, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_common_call_keeps_local_options(self):
        with patch.object(llm_service, "call_model", new_callable=AsyncMock, return_value="ok") as call:
            coroutine = llm_service.call_llm("question", temperature=0.7, num_predict=42)
            with self.assertRaises(StopIteration) as completed:
                coroutine.send(None)
            self.assertEqual(completed.exception.value, "ok")
        call.assert_awaited_once_with(
            llm_service.LLM_MODEL, "question", temperature=0.7, think=False, num_predict=42,
        )

    def test_qchv_keeps_its_own_request_options(self):
        response = Mock()
        response.json.return_value = {"message": {"content": "answer"}}
        with patch.object(quyche_llm_service.requests, "post", return_value=response) as post:
            service = quyche_llm_service.QuyCheLLMService()
            self.assertEqual(service._call_llm([], temperature=0.6, num_predict=99), "answer")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], llm_service.LLM_MODEL)
        self.assertFalse(payload["think"])
        self.assertEqual(payload["options"], {"temperature": 0.6, "num_predict": 99})
