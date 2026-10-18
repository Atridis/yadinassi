"""Notification tests are offline: all Telegram responses are mocked."""
import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

from scripts import notify_native_1c as notification


class NativeNotificationTests(unittest.TestCase):
    def setUp(self):
        self.event = {
            "action": "labeled", "label": {"name": notification.LABEL},
            "repository": {"full_name": notification.REPOSITORY},
            "pull_request": {
                "number": 42, "state": "open", "draft": True,
                "base": {"ref": "main", "repo": {"full_name": notification.REPOSITORY}},
                "head": {"repo": {"full_name": "external/fork"}},
                "title": "$(echo injection)", "body": "<a href='bad'>bad</a>",
                "html_url": "https://evil.invalid",
            },
        }
        self.env = {
            "GITHUB_EVENT_NAME": "pull_request_target",
            "GITHUB_REPOSITORY": notification.REPOSITORY,
            "GITHUB_RUN_ATTEMPT": "1",
            "TELEGRAM_BOT_TOKEN": "123456:FAKE_TEST_TOKEN",
            "TELEGRAM_CHAT_ID": "123456",
        }
        self.opener = MagicMock()
        self.response = self.opener.open.return_value.__enter__.return_value
        self.response.status = 200
        self.response.read.return_value = b'{"ok": true}'

    def run_notify(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = notification.notify(self.event, self.env, self.opener)
        if self.env.get("TELEGRAM_BOT_TOKEN"):
            self.assertNotIn(self.env["TELEGRAM_BOT_TOKEN"], output.getvalue())
        return code, output.getvalue()

    def test_explicit_fork_draft_request_is_safe_plain_text(self):
        self.assertEqual(self.run_notify()[0], 0)
        self.opener.open.assert_called_once()
        request = self.opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.telegram.org/bot123456:FAKE_TEST_TOKEN/sendMessage")
        self.assertEqual(request.method, "POST")
        self.assertEqual(self.opener.open.call_args.kwargs, {"timeout": 15})
        payload = json.loads(request.data)
        self.assertEqual(payload["chat_id"], "123456")
        self.assertIn("https://github.com/Atridis/yadinassi/pull/42", payload["text"])
        self.assertIn("реальной 1С", payload["text"])
        self.assertNotIn("evil", payload["text"])
        self.assertNotIn("injection", payload["text"])
        self.assertNotIn("parse_mode", payload)
        self.assertEqual(payload["link_preview_options"], {"is_disabled": True})

    def test_irrelevant_events_do_not_send(self):
        for key, value in (("action", "synchronize"), ("action", "opened"),
                           ("action", "unlabeled"), ("label", {"name": "bug"}),
                           ("repository", {"full_name": "fork/repo"})):
            with self.subTest(key=key, value=value):
                event = copy.deepcopy(self.event)
                event[key] = value
                self.assertFalse(notification.eligible(event, self.env))
        for key, value in (("GITHUB_EVENT_NAME", "pull_request"),
                           ("GITHUB_REPOSITORY", "fork/repo"),
                           ("GITHUB_RUN_ATTEMPT", "2")):
            with self.subTest(key=key):
                self.env[key] = value
                self.assertEqual(self.run_notify()[0], 0)
                self.env = dict(self.env, **{key: {
                    "GITHUB_EVENT_NAME": "pull_request_target",
                    "GITHUB_REPOSITORY": notification.REPOSITORY,
                    "GITHUB_RUN_ATTEMPT": "1",
                }[key]})
        self.opener.open.assert_not_called()

    def test_closed_wrong_base_and_invalid_numbers(self):
        for change in ({"state": "closed"}, {"number": True}, {"number": -1},
                       {"number": "42\n::error::injected"}, {"number": None},
                       {"base": {"ref": "other", "repo": {"full_name": notification.REPOSITORY}}},
                       {"base": {"ref": "main", "repo": {"full_name": "evil/fork"}}}):
            with self.subTest(change=change):
                event = copy.deepcopy(self.event)
                event["pull_request"].update(change)
                self.assertFalse(notification.eligible(event, self.env))

    def test_missing_configuration_fails_without_network(self):
        for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
            env = self.env.copy()
            env[key] = ""
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(notification.notify(self.event, env, self.opener), 1)
            self.assertIn("Configure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID", output.getvalue())
        self.opener.open.assert_not_called()

    def test_invalid_destination_and_token_fail_without_network(self):
        for key, value in (("TELEGRAM_CHAT_ID", "-100123"), ("TELEGRAM_CHAT_ID", "@channel"),
                           ("TELEGRAM_CHAT_ID", "0"), ("TELEGRAM_CHAT_ID", "123\n"),
                           ("TELEGRAM_BOT_TOKEN", "123:a/../../evil"),
                           ("TELEGRAM_BOT_TOKEN", "123:a?query")):
            env = dict(self.env, **{key: value})
            with self.subTest(key=key, value=value), redirect_stdout(io.StringIO()):
                self.assertEqual(notification.notify(self.event, env, self.opener), 1)
        self.opener.open.assert_not_called()

    def test_network_errors_are_redacted_and_never_retried(self):
        for error in (TimeoutError(self.env["TELEGRAM_BOT_TOKEN"]),
                      urllib.error.HTTPError("https://token.invalid/" + self.env["TELEGRAM_BOT_TOKEN"],
                                             401, self.env["TELEGRAM_BOT_TOKEN"], {}, None),
                      urllib.error.URLError(self.env["TELEGRAM_BOT_TOKEN"])):
            with self.subTest(error=type(error)):
                self.opener.reset_mock()
                self.opener.open.side_effect = error
                code, output = self.run_notify()
                self.assertEqual(code, 1)
                self.assertIn("failed or is uncertain", output)
                self.opener.open.assert_called_once()

    def test_rejected_and_malformed_responses_are_redacted(self):
        for body in (b'{"ok": false}', b'{}', b'[]', b'{"ok": 1}',
                     self.env["TELEGRAM_BOT_TOKEN"].encode()):
            with self.subTest(body=body):
                self.response.read.return_value = body
                self.assertEqual(self.run_notify()[0], 1)
        self.response.read.return_value = b'{"ok": true}'
        self.response.status = 503
        self.assertEqual(self.run_notify()[0], 1)

    def test_redirects_are_not_followed(self):
        self.assertIsNone(notification.NoRedirect().redirect_request(
            None, None, 307, "redirect", {}, "https://evil.invalid"))

    def test_default_opener_disables_redirects(self):
        with patch.object(notification.urllib.request, "build_opener", return_value=self.opener) as build:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(notification.notify(self.event, self.env), 0)
            self.assertIsInstance(build.call_args.args[0], notification.NoRedirect)

    def test_main_malformed_input_never_logs_secrets(self):
        with patch.dict(notification.os.environ, self.env, clear=True), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(notification.main(), 1)
        self.assertNotIn(self.env["TELEGRAM_BOT_TOKEN"], output.getvalue())

    def test_workflow_contract(self):
        workflow = (Path(__file__).resolve().parents[1] /
                    ".github/workflows/notify-native-1c.yml").read_text(encoding="utf-8")
        self.assertIn("types: [labeled]", workflow)
        self.assertIn("branches: [main]", workflow)
        self.assertIn("ref: ${{ github.event.pull_request.base.sha }}", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("github.run_attempt == 1", workflow)
        self.assertNotIn("head.sha", workflow)
        self.assertNotIn("secrets: inherit", workflow)
        self.assertNotIn("write", workflow)
        self.assertIn("python3 -I scripts/notify_native_1c.py", workflow)
