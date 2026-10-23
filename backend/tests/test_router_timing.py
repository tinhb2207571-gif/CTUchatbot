import unittest
from unittest.mock import AsyncMock, patch

from app.services.common import llm_service


def complete(coroutine):
    # Các dependency async được mock trả ngay, không mở event loop/network.
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    finally:
        coroutine.close()
    raise AssertionError("Unexpected asynchronous work in timing test")


class RouterTimingTests(unittest.TestCase):
    def test_rule_reports_zero_llm_time_without_calling_model(self):
        with patch.object(llm_service, "_high_confidence_domain", return_value=("THONG_BAO", "keyword")), patch.object(
            llm_service, "call_model_json", new_callable=AsyncMock
        ) as model, patch.object(llm_service, "log_event") as log:
            result = complete(llm_service.LLMService().classify_domain("test"))
        self.assertEqual(result, "THONG_BAO")
        model.assert_not_awaited()
        log.assert_called_once()
        self.assertEqual(log.call_args.kwargs["method"], "rule")
        self.assertEqual(log.call_args.kwargs["llm_ms"], 0)
        self.assertGreaterEqual(log.call_args.kwargs["total_ms"], 0)

    def test_llm_reports_separate_request_and_total_times(self):
        with patch.object(llm_service, "_high_confidence_domain", return_value=(None, None)), patch.object(
            llm_service, "call_model_json", new_callable=AsyncMock, return_value={"domain": "QCHV"}
        ) as model, patch.object(llm_service, "now", side_effect=[10, 11]), patch.object(
            llm_service, "elapsed_ms", side_effect=[1200, 2200]
        ) as timer, patch.object(llm_service, "log_event") as log:
            result = complete(llm_service.LLMService().classify_domain("test"))
        self.assertEqual(result, "QCHV")
        model.assert_awaited_once()
        self.assertEqual(timer.call_args_list[0].args, (11,))
        self.assertEqual(timer.call_args_list[1].args, (10,))
        self.assertEqual(log.call_args.kwargs["method"], "llm")
        self.assertEqual(log.call_args.kwargs["llm_ms"], 1200)
        self.assertEqual(log.call_args.kwargs["total_ms"], 2200)
        self.assertFalse(log.call_args.kwargs["fallback"])

    def test_invalid_llm_output_keeps_existing_fallback(self):
        with patch.object(llm_service, "_high_confidence_domain", return_value=(None, None)), patch.object(
            llm_service, "call_model_json", new_callable=AsyncMock, return_value={"domain": "invalid"}
        ), patch.object(llm_service, "log_event") as log:
            result = complete(llm_service.LLMService().classify_domain("test"))
        self.assertEqual(result, "CTDT")
        self.assertTrue(log.call_args.kwargs["fallback"])

    def test_failed_llm_request_logs_duration_and_still_raises(self):
        with patch.object(llm_service, "_high_confidence_domain", return_value=(None, None)), patch.object(
            llm_service, "call_model_json", new_callable=AsyncMock, side_effect=RuntimeError("offline")
        ), patch.object(llm_service, "log_event") as log:
            with self.assertRaisesRegex(RuntimeError, "offline"):
                complete(llm_service.LLMService().classify_domain("test"))
        self.assertEqual(log.call_args.kwargs["status"], "error")
        self.assertGreaterEqual(log.call_args.kwargs["llm_ms"], 0)
