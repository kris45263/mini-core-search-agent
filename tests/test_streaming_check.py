"""通过实际接收器验证开发脚本的交互与历史，不访问真实服务。"""

import importlib.util
import io
import json
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from test_deepseek_stream import ByteStream, event, DONE


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("scripts.check_streaming"), "需要开发验收脚本")
        from scripts import check_streaming
        self.module = check_streaming

    def test_followup_failure_interrupt_and_recovery(self):
        histories, streams = [], []
        def handler(request):
            messages = json.loads(request.content)["messages"]
            histories.append(messages)
            question = messages[-1]["content"]
            if question == "失败":
                chunks = [event("残稿"), httpx.ReadError("SECRET")]
            elif question == "中断":
                chunks = [event("片段"), KeyboardInterrupt()]
            else:
                chunks = [event("答："), event(question, "stop"), DONE]
            stream = ByteStream(chunks)
            streams.append(stream)
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=stream)
        client = httpx.Client(transport=httpx.MockTransport(handler))
        out, err = io.StringIO(), io.StringIO()
        with patch.object(self.module, "read_config", return_value={"DEEPSEEK_API_KEY": "fake", "DEEPSEEK_MODEL": "test"}), \
             patch.object(self.module.httpx, "Client", return_value=client), \
             patch("builtins.input", side_effect=["", "第一问", "失败", "中断", "第二问", "/exit"]), \
             redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(self.module.main(), 0)
        self.assertEqual([len(h) for h in histories], [2, 4, 4, 4])
        self.assertEqual(histories[-1][2], {"role": "assistant", "content": "答：第一问"})
        self.assertEqual(out.getvalue(), "答：第一问\n残稿\n片段\n答：第二问\n")
        self.assertIn("不会加入后续对话", err.getvalue())
        self.assertNotIn("SECRET", err.getvalue())
        self.assertIn("首段", err.getvalue())
        self.assertNotIn("你：", out.getvalue())
        self.assertTrue(client.is_closed)
        self.assertTrue(all(s.closed for s in streams))

    def test_config_requires_only_deepseek_and_does_not_interpolate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("DEEPSEEK_API_KEY=test\nDEEPSEEK_MODEL=m\n", encoding="utf-8-sig")
            self.assertEqual(self.module.read_config(path), {"DEEPSEEK_API_KEY": "test", "DEEPSEEK_MODEL": "m"})
            for text in ("DEEPSEEK_MODEL=m", "DEEPSEEK_API_KEY=${SAMPLE}\nDEEPSEEK_MODEL=m"):
                path.write_text(text, encoding="utf-8")
                with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "environment", "SAMPLE": "environment"}), self.assertRaises(ValueError):
                    self.module.read_config(path)

    def test_waiting_input_eof_and_interrupt_exit(self):
        for exception in (EOFError, KeyboardInterrupt):
            with patch.object(self.module, "read_config", return_value={"DEEPSEEK_API_KEY": "fake", "DEEPSEEK_MODEL": "m"}), \
                 patch("builtins.input", side_effect=exception), redirect_stderr(io.StringIO()):
                self.assertEqual(self.module.main(), 0)

    def test_config_failure_does_not_start_client(self):
        with patch.object(self.module, "read_config", side_effect=ValueError("缺配置")), \
             patch.object(self.module.httpx, "Client") as factory, redirect_stderr(io.StringIO()):
            self.assertEqual(self.module.main(), 1)
            factory.assert_not_called()

    def test_stdout_failure_closes_stream_and_stops_input(self):
        class Broken(io.StringIO):
            def write(self, text):
                raise BrokenPipeError()
        stream = ByteStream([event("正文"), event(finish="stop"), DONE])
        client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200,
            headers={"content-type": "text/event-stream"}, stream=stream)))
        with patch.object(self.module, "read_config", return_value={"DEEPSEEK_API_KEY": "fake", "DEEPSEEK_MODEL": "m"}), \
             patch.object(self.module.httpx, "Client", return_value=client), \
             patch("builtins.input", side_effect=["问题", "不应该读取"]) as inputs, \
             redirect_stdout(Broken()), redirect_stderr(io.StringIO()):
            self.assertEqual(self.module.main(), 1)
            self.assertEqual(inputs.call_count, 1)
        self.assertTrue(stream.closed)

    def test_finish_failure_reports_output_error_and_exits(self):
        class Broken(io.StringIO):
            def write(self, text):
                if text == "\n":
                    raise OSError()
                return super().write(text)
        stream = ByteStream([event("正文", "stop"), DONE])
        client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200,
            headers={"content-type": "text/event-stream"}, stream=stream)))
        err = io.StringIO()
        with patch.object(self.module, "read_config", return_value={"DEEPSEEK_API_KEY": "fake", "DEEPSEEK_MODEL": "m"}), \
             patch.object(self.module.httpx, "Client", return_value=client), \
             patch("builtins.input", return_value="问题") as inputs, \
             redirect_stdout(Broken()), redirect_stderr(err):
            self.assertEqual(self.module.main(), 1)
            self.assertEqual(inputs.call_count, 1)
        self.assertIn("输出", err.getvalue())
        self.assertNotIn("未保存", err.getvalue())

    def test_http_and_protocol_errors_do_not_disclose_raw_body(self):
        responses = [httpx.Response(401, json={"error": "SECRET"}),
                     httpx.Response(200, headers={"content-type": "text/event-stream"},
                                    stream=ByteStream([b"data: SECRET\n\n"]))]
        client = httpx.Client(transport=httpx.MockTransport(lambda r: responses.pop(0)))
        err = io.StringIO()
        with patch.object(self.module, "read_config", return_value={"DEEPSEEK_API_KEY": "fake", "DEEPSEEK_MODEL": "m"}), \
             patch.object(self.module.httpx, "Client", return_value=client), \
             patch("builtins.input", side_effect=["一", "二", "/exit"]), \
             redirect_stdout(io.StringIO()), redirect_stderr(err):
            self.assertEqual(self.module.main(), 0)
        self.assertIn("401", err.getvalue())
        self.assertNotIn("SECRET", err.getvalue())
