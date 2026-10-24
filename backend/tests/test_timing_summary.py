import asyncio
import unittest
from unittest.mock import patch

from app.services.common import pipeline_logger as pl


class TimingSummaryTests(unittest.TestCase):
    def test_summary_shows_stages_router_generation_and_totals(self):
        with patch.object(pl.logger, "info") as output, patch.dict("os.environ", {"PIPELINE_LOG_ENABLED": "1"}):
            with pl.chat_timing_summary("Test question"):
                pl.log_event("ROUTER", "result", domain="THONG_BAO", method="rule", total_ms=1, llm_ms=0)
                pl.log_event("THONG_BAO", "embedding", elapsed_ms=100)
                pl.log_event("THONG_BAO", "retrieval", elapsed_ms=200)
                pl.log_event("THONG_BAO", "generation", elapsed_ms=300)
                pl.log_event("CHAT", "done", domain="THONG_BAO", total_ms=650, branch_ms=649)
        summary = output.call_args.args
        self.assertIn("TIMING_SUMMARY", summary[0])
        self.assertEqual(summary[2], "THONG_BAO")
        self.assertIn("Router — rule", summary[5])
        self.assertIn("Tạo embedding câu hỏi", summary[5])
        self.assertIn("LLM sinh đáp án", summary[5])
        self.assertIn("Tổng nhánh THONG_BAO", summary[5])
        self.assertIn("0.650 s", summary[5])
        self.assertIsNone(pl._request_timings.get())

    def test_error_still_prints_summary_and_preserves_exception(self):
        with patch.object(pl.logger, "info") as output:
            with self.assertRaisesRegex(RuntimeError, "offline"):
                with pl.chat_timing_summary("test"):
                    pl.log_event("ROUTER", "result", method="llm", total_ms=120, llm_ms=100)
                    raise RuntimeError("offline")
        self.assertEqual(output.call_args.args[3], "Bị ngắt hoặc gặp lỗi")
        self.assertIsNone(pl._request_timings.get())

    def test_logging_can_still_be_disabled(self):
        with patch.object(pl.logger, "info") as output, patch.dict("os.environ", {"PIPELINE_LOG_ENABLED": "0"}):
            with pl.chat_timing_summary("test"):
                pl.log_event("THONG_BAO", "generation", elapsed_ms=20)
        output.assert_not_called()

    def test_skipped_vector_search_is_not_reported_as_executed(self):
        with patch.object(pl.logger, "info") as output:
            with pl.chat_timing_summary("test"):
                pl.log_event("CTDT", "vector_retrieval", elapsed_ms=0.1, executed=False)
        self.assertIn("Bỏ qua", output.call_args.args[5])


class ConcurrentTimingTests(unittest.IsolatedAsyncioTestCase):
    async def test_requests_are_isolated_and_thread_timings_are_collected(self):
        async def run(query, duration):
            with pl.chat_timing_summary(query):
                await asyncio.to_thread(pl.log_event, "QCHV", "retrieval", elapsed_ms=duration)
                await asyncio.sleep(0)

        with patch.object(pl.logger, "info") as output:
            await asyncio.gather(run("one", 111), run("two", 222))
        summaries = {call.args[4]: call.args[5] for call in output.call_args_list if "TIMING_SUMMARY" in call.args[0]}
        self.assertEqual(len(summaries), 2)
        self.assertIn("0.111 s", summaries["one"])
        self.assertNotIn("0.222 s", summaries["one"])
        self.assertIn("0.222 s", summaries["two"])
        self.assertNotIn("0.111 s", summaries["two"])
        self.assertIsNone(pl._request_timings.get())
