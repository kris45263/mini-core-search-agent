"""统一展示入口的行为约定；不调用真实服务。"""

import io
import json
import unittest
from contextlib import redirect_stdout, redirect_stderr

from seekra.display import AgentDisplay
from seekra.agent import run_agent
from seekra.session import Session
import httpx

from test_agent import reply, call


class DisplayEventTests(unittest.TestCase):
    def test_display_alone_renders_verbose_lifecycle_without_reprinting_content(self):
        """完整诊断由展示对象提供，不依赖 Agent 再建立隐藏输出器。"""
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            view = AgentDisplay(verbose=True)
            view.event('start', question='问题')
            view.event('model_call', round=1, message_count=2, remaining=11)
            view.content('唯一正文')
            view.event('model_response', content='唯一正文', tool_calls=None)
            view.event('final_answer', round=1)
        self.assertEqual(out.getvalue(), '唯一正文\n')
        self.assertNotIn('唯一正文', err.getvalue())
        self.assertIn('上下文 2 条消息', err.getvalue())
        self.assertIn('模型决定：直接回答', err.getvalue())

    def test_collector_receives_events_without_terminal_output(self):
        """采集实验事件不要求创建终端视图，返回答案仍可独立消费。"""
        events = []
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), httpx.Client(
                transport=httpx.MockTransport(lambda request: reply('答案'))) as client:
            answer = run_agent('问题', client=client, model='test',
                               deepseek_api_key='fake-ds', tavily_api_key='fake-tv',
                               on_event=lambda event, **details: events.append((event, details)))
        self.assertEqual(answer, '答案')
        self.assertEqual((out.getvalue(), err.getvalue()), ('', ''))
        self.assertEqual([event for event, _ in events],
                         ['start', 'model_call', 'model_response', 'final_answer'])

    def test_broken_diagnostics_preserve_requests_answer_and_session(self):
        """诊断写入或刷新故障都不影响真实循环、正文及成功提交。"""
        class BrokenWrite(io.StringIO):
            def write(self, text):
                raise OSError('诊断输出不可写')

        class BrokenFlush(io.StringIO):
            def flush(self):
                raise OSError('诊断输出不可刷新')

        runs = []
        for error_stream in (io.StringIO(), BrokenWrite(), BrokenFlush()):
            requests, out, session = [], io.StringIO(), Session()

            def handler(request):
                body = json.loads(request.content)
                requests.append(body)
                if len(requests) == 1:
                    return reply('先整理', [call('think_tool', {'reflection': '观察'})])
                return reply('最终答案')

            with redirect_stdout(out), redirect_stderr(error_stream), httpx.Client(
                    transport=httpx.MockTransport(handler)) as client:
                view = AgentDisplay(verbose=True)
                answer = run_agent('问题', client=client, model='test',
                                   deepseek_api_key='fake-ds', tavily_api_key='fake-tv',
                                   session=session, on_event=view.event, on_content=view.content)
            runs.append((requests, answer, session.messages, session.pages, out.getvalue()))
        self.assertEqual(runs[0], runs[1])
        self.assertEqual(runs[0], runs[2])
        self.assertEqual(runs[0][-1], '先整理\n最终答案\n')

    def test_model_line_finishes_before_tool_status(self):
        """两条标准流共享终端时，工具状态必须出现在完整正文行之后。"""
        terminal = io.StringIO()
        with redirect_stdout(terminal), redirect_stderr(terminal):
            view = AgentDisplay()
            view.content('先查资料')
            view.event('model_response', content='先查资料')
            view.event('tool_call', tool_call=call('tavily_search', {'query': '关键词'}))
        self.assertTrue(terminal.getvalue().startswith('先查资料\n正在搜索'))


if __name__ == '__main__':
    unittest.main()
