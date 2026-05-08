from __future__ import annotations

import os
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.live_preflight import PREFLIGHT_READY_BUT_EXECUTION_DISABLED, PROMOTED_STRATEGY_KEY
from src.app.hammer_radar.operator.notification_watcher import append_alert_record
from src.app.hammer_radar.operator.operator_actions import parse_operator_action
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.telegram_approval_challenge import (
    create_first_live_approval_challenge,
    load_telegram_approval_challenges,
    process_first_live_challenge_reply,
)
from src.app.hammer_radar.operator.telegram_operator_bridge import (
    handle_telegram_operator_command,
    load_telegram_operator_commands,
)
from src.app.hammer_radar.operator.telegram_polling_worker import poll_telegram_once, telegram_polling_state_path
from src.app.hammer_radar.operator.telegram_polling_worker import build_arg_parser, polling_state, polling_status


class TelegramOperatorBridgeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_help_returns_command_list(self) -> None:
        payload = handle_telegram_operator_command(text="HELP", log_dir=self.log_dir)

        self.assertEqual("ACCEPTED", payload["result_status"])
        self.assertIn("FIRST LIVE CHECK", payload["message"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["secrets_shown"])

    def test_status_commands_return_messages(self) -> None:
        for text in (
            "FIRST LIVE CHECK",
            "FIRST LIVE RUNBOOK",
            "LIVE PREFLIGHT",
            "PROMOTION STATUS",
            "CONNECTOR STATUS",
            "PROTECTIVE STATUS",
            "READINESS STATUS",
        ):
            with self.subTest(text=text):
                payload = handle_telegram_operator_command(text=text, log_dir=self.log_dir)
                self.assertEqual("ACCEPTED", payload["result_status"])
                self.assertFalse(payload["order_placed"])
                self.assertFalse(payload["real_order_placed"])

    def test_first_live_next_uses_fast_chain_status(self) -> None:
        with patch.multiple(
            "src.app.hammer_radar.operator.first_live_chain_runbook",
            build_first_live_test_order_status=unittest.mock.Mock(side_effect=AssertionError("R64 should be skipped")),
            build_first_live_ladder_submit_status=unittest.mock.Mock(side_effect=AssertionError("R62 should be skipped")),
            build_first_live_protective_status=unittest.mock.Mock(side_effect=AssertionError("R63 should be skipped")),
        ):
            payload = handle_telegram_operator_command(text="FIRST LIVE NEXT", log_dir=self.log_dir)

        self.assertEqual("ACCEPTED", payload["result_status"])
        self.assertEqual("fast", payload["performance"]["mode"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])

    def test_first_live_evaluate_records_safely(self) -> None:
        payload = handle_telegram_operator_command(text="FIRST LIVE EVALUATE", log_dir=self.log_dir)

        self.assertEqual("ACCEPTED", payload["result_status"])
        self.assertIn("recorded=True", payload["message"])
        self.assertFalse(payload["order_placed"])

    def test_approve_paper_rejects_without_unambiguous_candidate(self) -> None:
        payload = handle_telegram_operator_command(text="APPROVE PAPER", log_dir=self.log_dir)

        self.assertEqual("REJECTED", payload["result_status"])
        self.assertIn("No unambiguous paper candidate", payload["message"])
        self.assertFalse(payload["order_placed"])

    def test_approve_paper_records_paper_only_for_8m_short(self) -> None:
        self._append_alert_candidate(self._paper_short_candidate())

        payload = handle_telegram_operator_command(text="APPROVE PAPER", log_dir=self.log_dir)

        self.assertEqual("ACCEPTED", payload["result_status"])
        self.assertIn("Paper/manual intent recorded only", payload["message"])
        self.assertIn("not live approval eligible", payload["message"])
        self.assertEqual("BTCUSDT|8m|short|2026-05-05T10:00:00+00:00", payload["related_signal_id"])
        self.assertFalse(payload["order_placed"])

    def test_challenge_blocked_when_no_fresh_promoted_signal(self) -> None:
        payload = create_first_live_approval_challenge(log_dir=self.log_dir)

        self.assertEqual("BLOCKED", payload["result_status"])
        self.assertIn("no fresh promoted signal", payload["blockers"])
        self.assertIsNone(payload["challenge"])

    def test_paper_only_8m_short_cannot_create_live_challenge(self) -> None:
        payload = create_first_live_approval_challenge(preflight_pack=self._ready_pack(timeframe="8m", direction="short"), log_dir=self.log_dir)

        self.assertEqual("BLOCKED", payload["result_status"])
        self.assertIn("candidate timeframe is not 13m", payload["blockers"])
        self.assertIn("candidate direction is not long", payload["blockers"])

    def test_challenge_created_for_mocked_fresh_promoted_signal(self) -> None:
        payload = create_first_live_approval_challenge(preflight_pack=self._ready_pack(), log_dir=self.log_dir, ttl_seconds=90)

        self.assertEqual("ACCEPTED", payload["result_status"])
        self.assertEqual("CREATED", payload["challenge_status"])
        self.assertRegex(payload["challenge_code"], r"^[0-9a-f]{6,}$")
        self.assertIn("YES " + payload["challenge_code"], payload["message"])
        self.assertIn("BTCUSDT|13m|long|2026-05-05T10:00:00+00:00", payload["message"])
        self.assertIn("Entry: 100.0", payload["message"])
        records = load_telegram_approval_challenges(limit=10, log_dir=self.log_dir)
        self.assertEqual("<hidden>", records[0]["challenge_code_hash"])

    def test_yes_reply_rejections(self) -> None:
        raw_yes = process_first_live_challenge_reply(text="YES", log_dir=self.log_dir)
        unknown = process_first_live_challenge_reply(text="YES abc123", log_dir=self.log_dir)
        expired_created = create_first_live_approval_challenge(preflight_pack=self._ready_pack(), log_dir=self.log_dir, ttl_seconds=-1)
        expired = process_first_live_challenge_reply(text=f"YES {expired_created['challenge_code']}", log_dir=self.log_dir)

        self.assertEqual("REJECTED", raw_yes["result_status"])
        self.assertEqual("unknown challenge code", unknown["reason"])
        self.assertEqual("EXPIRED", expired["challenge_status"])

    def test_valid_yes_code_records_exact_approval_only_once(self) -> None:
        challenge = create_first_live_approval_challenge(preflight_pack=self._ready_pack(), log_dir=self.log_dir, ttl_seconds=90)

        approved = process_first_live_challenge_reply(text=f"YES {challenge['challenge_code']}", log_dir=self.log_dir)
        reused = process_first_live_challenge_reply(text=f"YES {challenge['challenge_code']}", log_dir=self.log_dir)

        self.assertEqual("ACCEPTED", approved["result_status"])
        self.assertEqual("APPROVED", approved["challenge_status"])
        self.assertIn("Approval is not execution", approved["message"])
        self.assertFalse(approved["order_placed"])
        self.assertFalse(approved["real_order_placed"])
        self.assertEqual("REJECTED", reused["result_status"])
        self.assertEqual("already used challenge code", reused["reason"])
        approvals_path = self.log_dir / "live_approval_requests.ndjson"
        self.assertTrue(approvals_path.exists())
        self.assertIn("LIVE APPROVE BTCUSDT|13m|long|2026-05-05T10:00:00+00:00", approvals_path.read_text(encoding="utf-8"))

    def test_api_endpoints_and_operator_actions(self) -> None:
        command = self.client.post("/telegram/operator-command", json={"text": "FIRST LIVE CHECK"}).json()
        help_payload = self.client.post("/telegram/operator-command", json={"text": "HELP"}).json()
        reply = self.client.post("/telegram/first-live/reply", json={"text": "YES"}).json()
        action = self.client.post("/operator/actions", json={"text": "FIRST LIVE CHALLENGE"}).json()
        blocked = self.client.post("/operator/actions", json={"text": "trade now live"}).json()
        challenges = self.client.get("/telegram/first-live/challenges").json()
        commands = self.client.get("/telegram/operator-commands").json()

        self.assertEqual("ACCEPTED", command["result_status"])
        self.assertIn("FIRST LIVE CHECK", str(help_payload))
        self.assertEqual("REJECTED", reply["result_status"])
        self.assertEqual("BLOCKED", action["result_status"])
        self.assertEqual("blocked_live_command", blocked["normalized_action"])
        self.assertFalse(blocked["order_placed"])
        self.assertFalse(challenges["secrets_shown"])
        self.assertFalse(commands["secrets_shown"])

    def test_operator_actions_yes_code_works(self) -> None:
        challenge = create_first_live_approval_challenge(preflight_pack=self._ready_pack(), log_dir=self.log_dir, ttl_seconds=90)

        payload = self.client.post("/operator/actions", json={"text": f"YES {challenge['challenge_code']}"}).json()

        self.assertEqual("ACCEPTED", payload["result_status"])
        self.assertIn("Approval recorded", payload["message"])
        self.assertFalse(payload["order_placed"])

    def test_parse_operator_action_recognizes_bridge_commands(self) -> None:
        self.assertEqual("telegram_operator_command", parse_operator_action("HELP")["normalized_action"])
        self.assertEqual("telegram_operator_command", parse_operator_action("YES abc123")["normalized_action"])
        self.assertEqual("REJECTED", parse_operator_action("YES")["result_status"])

    def test_polling_worker_routes_fake_update_without_exposing_token(self) -> None:
        transport = _FakeTelegramTransport()
        env = {"TELEGRAM_BOT_TOKEN": "secret-token", "TELEGRAM_CHAT_ID": "123"}
        payload = poll_telegram_once(env=env, log_dir=self.log_dir, transport=transport, send_responses=True)
        commands = load_telegram_operator_commands(limit=10, log_dir=self.log_dir)

        self.assertEqual("OK", payload["status"])
        self.assertEqual([101], [item["update_id"] for item in payload["processed"]])
        self.assertTrue(telegram_polling_state_path(self.log_dir).exists())
        self.assertEqual("<token>", transport.tokens[0])
        self.assertNotIn("secret-token", str(payload))
        self.assertEqual("help", commands[0]["normalized_action"])

    def test_polling_status_and_state_are_sanitized(self) -> None:
        env = {"TELEGRAM_BOT_TOKEN": "secret-token", "TELEGRAM_CHAT_ID": "123"}
        status = polling_status(env=env, log_dir=self.log_dir)
        state = polling_state(log_dir=self.log_dir)

        self.assertTrue(status["token_present"])
        self.assertTrue(status["chat_id_configured"])
        self.assertFalse(status["secrets_shown"])
        self.assertNotIn("secret-token", str(status))
        self.assertFalse(state["secrets_shown"])

    def test_polling_api_endpoints_are_one_shot_and_safe(self) -> None:
        status = self.client.get("/telegram/polling/status")
        state = self.client.get("/telegram/polling/state")
        once = self.client.post("/telegram/polling/once", json={"dry_run": True})

        self.assertEqual(200, status.status_code)
        self.assertFalse(status.json()["secrets_shown"])
        self.assertEqual(200, state.status_code)
        self.assertFalse(state.json()["secrets_shown"])
        self.assertEqual(200, once.status_code)
        self.assertIn(once.json()["result_status"], {"BLOCKED", "ACCEPTED"})
        self.assertFalse(once.json()["order_placed"])
        self.assertFalse(once.json()["real_order_placed"])

    def test_polling_dedupes_old_update_and_persists_last_update_id(self) -> None:
        transport = _UpdatesTransport([{"update_id": 5, "message": {"text": "HELP", "chat": {"id": 123}}}])
        env = {"TELEGRAM_BOT_TOKEN": "secret-token", "TELEGRAM_CHAT_ID": "123"}
        first = poll_telegram_once(env=env, log_dir=self.log_dir, transport=transport, send_responses=False)
        second = poll_telegram_once(env=env, log_dir=self.log_dir, transport=transport, send_responses=False)
        state = polling_state(log_dir=self.log_dir)["state"]

        self.assertEqual(5, state["last_update_id"])
        self.assertEqual("PROCESSED", first["processed"][0]["status"])
        self.assertEqual("DEDUPED_OLD_UPDATE", second["processed"][0]["status"])

    def test_polling_non_text_update_is_ignored_safely(self) -> None:
        transport = _UpdatesTransport([{"update_id": 7, "message": {"photo": [], "chat": {"id": 123}}}])
        env = {"TELEGRAM_BOT_TOKEN": "secret-token", "TELEGRAM_CHAT_ID": "123"}

        payload = poll_telegram_once(env=env, log_dir=self.log_dir, transport=transport)

        self.assertEqual("IGNORED_NON_TEXT", payload["processed"][0]["status"])
        self.assertEqual([], load_telegram_operator_commands(limit=10, log_dir=self.log_dir))

    def test_polling_dry_run_does_not_send_message(self) -> None:
        transport = _UpdatesTransport([{"update_id": 9, "message": {"text": "HELP", "chat": {"id": 123}}}])
        env = {"TELEGRAM_BOT_TOKEN": "secret-token", "TELEGRAM_CHAT_ID": "123"}

        payload = poll_telegram_once(env=env, log_dir=self.log_dir, transport=transport, send_responses=True, dry_run=True)

        self.assertEqual("PROCESSED", payload["processed"][0]["status"])
        self.assertEqual(0, transport.send_count)
        self.assertFalse(payload["processed"][0]["message_sent"])

    def test_polling_fake_send_records_sanitized_send_result(self) -> None:
        transport = _UpdatesTransport([{"update_id": 11, "message": {"text": "HELP", "chat": {"id": 123}}}])
        env = {"TELEGRAM_BOT_TOKEN": "secret-token", "TELEGRAM_CHAT_ID": "123"}

        payload = poll_telegram_once(env=env, log_dir=self.log_dir, transport=transport, send_responses=True)
        send_result = payload["processed"][0]["send_result"]

        self.assertEqual(1, transport.send_count)
        self.assertTrue(send_result["network_used"])
        self.assertTrue(send_result["message_sent"])
        self.assertFalse(send_result["secrets_shown"])
        self.assertNotIn("secret-token", str(payload))

    def test_polling_routes_raw_yes_and_trade_now_live_safely(self) -> None:
        updates = [
            {"update_id": 21, "message": {"text": "YES", "chat": {"id": 123}}},
            {"update_id": 22, "message": {"text": "trade now live", "chat": {"id": 123}}},
        ]
        env = {"TELEGRAM_BOT_TOKEN": "secret-token", "TELEGRAM_CHAT_ID": "123"}
        payload = poll_telegram_once(env=env, log_dir=self.log_dir, transport=_UpdatesTransport(updates), send_responses=False)
        commands = load_telegram_operator_commands(limit=10, log_dir=self.log_dir)

        self.assertEqual(["REJECTED", "BLOCKED"], [item["result_status"] for item in payload["processed"]])
        self.assertEqual("blocked_live_command", commands[0]["normalized_action"])
        self.assertEqual("challenge_reply", commands[1]["normalized_action"])

    def test_cli_parser_modes_without_running_loop(self) -> None:
        parser = build_arg_parser()
        once = parser.parse_args(["--once", "--dry-run"])
        loop = parser.parse_args(["--loop", "--interval", "3"])

        self.assertTrue(once.once)
        self.assertTrue(once.dry_run)
        self.assertTrue(loop.loop)
        self.assertEqual(3, loop.interval)

    def test_systemd_template_exists_but_not_installed(self) -> None:
        template = Path("ops/systemd/hammer-telegram-operator-polling.service.example")
        self.assertTrue(template.exists())
        text = template.read_text(encoding="utf-8")
        self.assertIn("--loop --interval 3", text)
        self.assertIn("User=josue", text)

    def test_no_env_changes_or_binance_network_calls(self) -> None:
        before = dict(os.environ)
        with patch("urllib.request.urlopen") as urlopen:
            handle_telegram_operator_command(text="CONNECTOR STATUS", log_dir=self.log_dir)
            create_first_live_approval_challenge(log_dir=self.log_dir)
        self.assertEqual(before, dict(os.environ))
        urlopen.assert_not_called()

    def _append_alert_candidate(self, candidate: dict) -> None:
        append_alert_record(
            {
                "alert_id": "alert-paper",
                "created_at": datetime.now(UTC).isoformat(),
                "alert_type": "ACTIONABLE_PAPER",
                "signal_id": candidate["signal_id"],
                "candidate": candidate,
                "telegram_sent": True,
                "live_execution_enabled": False,
                "order_placed": False,
            },
            log_dir=self.log_dir,
        )

    @staticmethod
    def _paper_short_candidate() -> dict:
        return {
            "signal_id": "BTCUSDT|8m|short|2026-05-05T10:00:00+00:00",
            "symbol": "BTCUSDT",
            "timeframe": "8m",
            "direction": "short",
            "decision": "PAPER_ONLY",
            "entry": 100.0,
            "stop": 101.0,
            "take_profit": 99.0,
        }

    @staticmethod
    def _ready_pack(*, timeframe: str = "13m", direction: str = "long") -> dict:
        signal_id = f"BTCUSDT|{timeframe}|{direction}|2026-05-05T10:00:00+00:00"
        return {
            "preflight_id": "preflight-ready",
            "preflight_status": PREFLIGHT_READY_BUT_EXECUTION_DISABLED,
            "promoted_strategy_ready": True,
            "matching_fresh_signal_found": True,
            "strategy_key": PROMOTED_STRATEGY_KEY,
            "candidate_signal_id": signal_id,
            "signal_id": signal_id,
            "readiness_status": "READY",
            "ticket_status": "PROPOSED",
            "dry_run_status": "VALID",
            "live_safety_status": "WOULD_BE_ALLOWED_IF_LIVE_ENABLED",
            "candidate": {
                "signal_id": signal_id,
                "symbol": "BTCUSDT",
                "timeframe": timeframe,
                "direction": direction,
                "entry": 100.0,
                "stop": 95.0,
                "take_profit": 105.0,
                "freshness_status": "fresh",
                "decision": "ELIGIBLE_TINY_LIVE",
                "tradable": True,
                "reject_reason": None,
            },
        }


class _FakeTelegramTransport:
    def __init__(self) -> None:
        self.tokens: list[str] = []

    def get_updates(self, *, token: str, offset: int | None) -> dict:
        self.tokens.append("<token>" if token else "")
        return {"ok": True, "result": [{"update_id": 101, "message": {"text": "HELP", "chat": {"id": 123}}}]}

    def send_message(self, *, token: str, chat_id: str, text: str) -> dict:
        self.tokens.append("<token>" if token else "")
        return {"ok": True}


class _UpdatesTransport:
    def __init__(self, updates: list[dict]) -> None:
        self.updates = updates
        self.send_count = 0

    def get_updates(self, *, token: str, offset: int | None) -> dict:
        return {"ok": True, "result": self.updates}

    def send_message(self, *, token: str, chat_id: str, text: str) -> dict:
        self.send_count += 1
        return {"ok": True, "result": {"chat_id": chat_id, "text_length": len(text)}}


if __name__ == "__main__":
    unittest.main()
