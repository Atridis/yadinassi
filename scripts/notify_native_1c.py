"""Send one explicit native-1C request; never execute or quote PR-controlled text."""
import json
import os
from pathlib import Path
import re
import sys
import urllib.request

REPOSITORY = "Atridis/yadinassi"
LABEL = "needs-native-1c-run"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Do not forward the token-bearing URL or message to another endpoint."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def eligible(event, env):
    pr = event.get("pull_request", {})
    return (
        env.get("GITHUB_EVENT_NAME") == "pull_request_target"
        and env.get("GITHUB_REPOSITORY") == REPOSITORY
        and env.get("GITHUB_RUN_ATTEMPT") == "1"
        and event.get("action") == "labeled"
        and event.get("label", {}).get("name") == LABEL
        and event.get("repository", {}).get("full_name") == REPOSITORY
        and pr.get("base", {}).get("repo", {}).get("full_name") == REPOSITORY
        and pr.get("base", {}).get("ref") == "main"
        and pr.get("state") == "open"
        and type(pr.get("number")) is int
        and pr["number"] > 0
    )


def notify(event, env, opener=None):
    if not eligible(event, env):
        print("Native 1C notification skipped: event is not an explicit request.")
        return 0
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("::error::Configure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID repository secrets.")
        return 1
    # Restrict URL components and destination to a private numeric chat ID.
    if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]+", token) or not re.fullmatch(r"[1-9][0-9]*", chat_id):
        print("::error::Invalid Telegram configuration; use a bot token and a positive private chat ID.")
        return 1
    number = event["pull_request"]["number"]
    text = (
        f"Для PR #{number} нужен ручной прогон на реальной 1С.\n"
        f"https://github.com/{REPOSITORY}/pull/{number}\n"
        "Пожалуйста, запустите интеграционные тесты из этого PR и обновите "
        "результаты в integrational_tests/output и сведения о прогоне в integrational_tests/meta.md."
    )
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps({
            "chat_id": chat_id, "text": text,
            "link_preview_options": {"is_disabled": True},
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # Never log exceptions, request URLs, or response bodies: they may contain secrets.
    # No automatic retries: a timed-out request may already have been delivered.
    try:
        if opener is None:
            opener = urllib.request.build_opener(NoRedirect())
        with opener.open(request, timeout=15) as response:
            result = json.loads(response.read(65536))
            if response.status != 200 or not isinstance(result, dict) or result.get("ok") is not True:
                raise ValueError("Telegram rejected request")
    except Exception:
        print("::error::Telegram delivery failed or is uncertain. Check configuration and the private chat before requesting again.")
        return 1
    print("Telegram accepted the native 1C run request.")
    return 0


def main():
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
        return notify(event, os.environ)
    except Exception:
        # Malformed events and local failures must not expose environment values.
        print("::error::Unable to process native 1C notification event.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
