from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from subprocess import run
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator import archive
from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.models import SignalRecord
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR


class ApprovalApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)})
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_health_returns_live_execution_disabled(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual("hammer_radar_approval_api", payload["service"])
        self.assertFalse(payload["live_execution_enabled"])

    def test_ui_returns_html_with_safety_text_and_buttons(self) -> None:
        for path in ("/", "/ui"):
            response = self.client.get(path)

            self.assertEqual(200, response.status_code)
            self.assertIn("text/html", response.headers["content-type"])
            html = response.text
            self.assertIn("LOCAL PAPER/MANUAL INTENT ONLY", html)
            self.assertIn("live_execution_enabled=false", html)
            self.assertIn("order_placed=false", html)
            self.assertIn("Record Decision", html)
            self.assertIn("Latest only", html)
            self.assertIn("Eligible only", html)
            self.assertIn("Allow short", html)
            self.assertIn("Friday Readiness", html)
            self.assertIn("Machine Trade Ticket", html)
            self.assertIn("Approve Paper Ticket", html)
            self.assertIn("Execute Paper Ticket", html)
            self.assertIn("No order will be placed", html)
            self.assertIn("This records approval intent only", html)
            self.assertIn("Paper execution only", html)
            self.assertIn("Paper Executions", html)
            self.assertIn("Exchange Dry Run", html)
            self.assertIn("No order was sent", html)
            self.assertIn("No API key used", html)
            self.assertIn("Live Safety Envelope", html)
            self.assertIn("Kill switch is active by default", html)
            self.assertIn("No live order can be placed", html)
            self.assertIn("44 USDT", html)
            self.assertIn("2x preferred", html)
            self.assertIn("3x max", html)
            self.assertIn("isolated margin", html)
            self.assertIn("Recent Decisions", html)
            self.assertIn("Watch", html)
            self.assertIn("Reject", html)
            self.assertIn("Paper Only", html)
            self.assertIn("Log Manual-Live Intent", html)
            self.assertIn("Blocked: candidate is FORBIDDEN", html)
            self.assertIn("No order placement", html)

    def test_candidates_returns_live_execution_disabled_and_decisions(self) -> None:
        archive.append_signal(self._eligible_signal(signal_id="eligible|1"), log_dir=self.log_dir)

        response = self.client.get("/candidates")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["order_placed"])
        self.assertEqual("ELIGIBLE_TINY_LIVE", payload["candidates"][0]["decision"])
        self.assertFalse(payload["candidates"][0]["order_placed"])

    def test_readiness_returns_safety_fields_and_not_ready_empty_archive(self) -> None:
        response = self.client.get("/readiness")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["order_placed"])
        self.assertEqual("NOT_READY", payload["readiness_status"])
        self.assertFalse(payload["allowed_now"])
        self.assertIn("no fresh ELIGIBLE_TINY_LIVE", payload["reason_summary"])

    def test_readiness_ready_with_fresh_eligible_candidate_and_no_manual_outcomes(self) -> None:
        archive.append_signal(self._eligible_signal(signal_id="eligible|ready"), log_dir=self.log_dir)

        response = self.client.get("/readiness")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("READY", payload["readiness_status"])
        self.assertTrue(payload["allowed_now"])
        self.assertEqual(1, payload["current_state"]["fresh_eligible_count"])
        self.assertEqual(0, payload["current_state"]["manual_outcomes_today"])

    def test_readiness_not_ready_when_candidate_is_expired(self) -> None:
        archive.append_signal(
            self._eligible_signal(
                signal_id="eligible|expired",
                timestamp=(datetime.now(UTC) - timedelta(minutes=90)).isoformat(),
            ),
            log_dir=self.log_dir,
        )

        response = self.client.get("/readiness")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("NOT_READY", payload["readiness_status"])
        self.assertFalse(payload["allowed_now"])
        self.assertIn("expired", payload["reason_summary"])

    def test_readiness_not_ready_when_manual_outcome_exists_today(self) -> None:
        archive.append_signal(self._eligible_signal(signal_id="eligible|used"), log_dir=self.log_dir)
        self.client.post(
            "/manual-outcomes",
            json={
                "signal_id": "eligible|used",
                "result": "skipped",
                "notes": "already reviewed today",
            },
        )

        response = self.client.get("/readiness")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("NOT_READY", payload["readiness_status"])
        self.assertEqual(1, payload["current_state"]["manual_outcomes_today"])
        self.assertIn("manual outcome already logged today", payload["blockers"])

    def test_readiness_not_ready_when_loss_exists_today(self) -> None:
        archive.append_signal(self._eligible_signal(signal_id="eligible|loss"), log_dir=self.log_dir)
        self.client.post(
            "/manual-outcomes",
            json={
                "signal_id": "eligible|loss",
                "result": "loss",
                "pnl_usd": -1.25,
                "notes": "loss today",
            },
        )

        response = self.client.get("/readiness")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("NOT_READY", payload["readiness_status"])
        self.assertEqual(1, payload["current_state"]["losses_today"])
        self.assertIn("at least one manual loss logged today", payload["blockers"])

    def test_approve_manual_live_records_decision_for_eligible_candidate(self) -> None:
        archive.append_signal(self._eligible_signal(signal_id="eligible|approve"), log_dir=self.log_dir)

        response = self.client.post(
            "/decisions",
            json={
                "signal_id": "eligible|approve",
                "decision": "approve_manual_live",
                "operator": "josue",
                "notes": "manual intent only",
                "intended_position_usd": 44,
                "intended_leverage": 2,
            },
        )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("approve_manual_live", payload["decision"])
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["order_placed"])
        self.assertEqual("ELIGIBLE_TINY_LIVE", payload["candidate_snapshot"]["decision"])
        self.assertTrue((self.log_dir / "manual_decisions.ndjson").exists())

    def test_reject_records_decision(self) -> None:
        response = self.client.post(
            "/decisions",
            json={
                "signal_id": "unknown|reject",
                "decision": "reject",
                "operator": "josue",
                "notes": "not interested",
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual("reject", response.json()["decision"])

    def test_paper_only_records_decision(self) -> None:
        response = self.client.post(
            "/decisions",
            json={
                "signal_id": "unknown|paper",
                "decision": "paper_only",
                "operator": "josue",
                "notes": "paper only",
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual("paper_only", response.json()["decision"])

    def test_approve_manual_live_rejects_forbidden_candidate(self) -> None:
        archive.append_signal(
            self._eligible_signal(
                signal_id="forbidden|1",
                tradable=False,
                reject_reason="strength_below_minimum",
                hammer_strength=60.0,
            ),
            log_dir=self.log_dir,
        )

        response = self.client.post(
            "/decisions",
            json={
                "signal_id": "forbidden|1",
                "decision": "approve_manual_live",
                "operator": "josue",
                "notes": "should fail",
                "override_reason": "still should not approve forbidden",
            },
        )

        self.assertEqual(400, response.status_code)
        self.assertIn("FORBIDDEN", response.json()["detail"])

    def test_approval_over_default_max_position_fails_unless_override_reason_provided(self) -> None:
        archive.append_signal(self._eligible_signal(signal_id="eligible|position"), log_dir=self.log_dir)

        failed = self.client.post(
            "/decisions",
            json={
                "signal_id": "eligible|position",
                "decision": "approve_manual_live",
                "operator": "josue",
                "intended_position_usd": 45,
            },
        )
        allowed = self.client.post(
            "/decisions",
            json={
                "signal_id": "eligible|position",
                "decision": "approve_manual_live",
                "operator": "josue",
                "intended_position_usd": 45,
                "override_reason": "manual cap exception",
            },
        )

        self.assertEqual(400, failed.status_code)
        self.assertEqual(200, allowed.status_code)

    def test_approval_over_default_max_leverage_fails_unless_override_reason_provided(self) -> None:
        archive.append_signal(self._eligible_signal(signal_id="eligible|leverage"), log_dir=self.log_dir)

        failed = self.client.post(
            "/decisions",
            json={
                "signal_id": "eligible|leverage",
                "decision": "approve_manual_live",
                "operator": "josue",
                "intended_leverage": 4,
            },
        )
        allowed = self.client.post(
            "/decisions",
            json={
                "signal_id": "eligible|leverage",
                "decision": "approve_manual_live",
                "operator": "josue",
                "intended_leverage": 4,
                "override_reason": "manual leverage exception",
            },
        )

        self.assertEqual(400, failed.status_code)
        self.assertEqual(200, allowed.status_code)

    def test_decisions_are_stored_in_selected_log_dir_and_listed(self) -> None:
        response = self.client.post(
            "/decisions",
            json={
                "signal_id": "list|1",
                "decision": "watch",
                "operator": "josue",
                "notes": "watching",
            },
        )
        decision_id = response.json()["decision_id"]

        list_response = self.client.get("/decisions")
        single_response = self.client.get(f"/decisions/{decision_id}")

        self.assertEqual(200, list_response.status_code)
        self.assertEqual(1, len(list_response.json()["decisions"]))
        self.assertEqual(200, single_response.status_code)
        self.assertEqual(decision_id, single_response.json()["decision_id"])
        self.assertTrue((self.log_dir / "manual_decisions.ndjson").exists())

    def test_no_live_order_placement_fields_are_true(self) -> None:
        response = self.client.post(
            "/decisions",
            json={
                "signal_id": "safe|1",
                "decision": "watch",
                "operator": "josue",
            },
        )

        payload = response.json()
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["order_placed"])

    def test_manual_outcome_api_writes_and_lists_records(self) -> None:
        response = self.client.post(
            "/manual-outcomes",
            json={
                "signal_id": "manual-api|1",
                "result": "skipped",
                "notes": "api unit test",
            },
        )
        list_response = self.client.get("/manual-outcomes")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("manual-api|1", payload["signal_id"])
        self.assertEqual("skipped", payload["result"])
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["order_placed"])
        self.assertEqual(200, list_response.status_code)
        listed = list_response.json()
        self.assertFalse(listed["live_execution_enabled"])
        self.assertFalse(listed["order_placed"])
        self.assertEqual(1, len(listed["manual_outcomes"]))
        self.assertTrue((self.log_dir / "manual_outcomes.ndjson").exists())

    def test_manual_outcome_api_rejects_invalid_result(self) -> None:
        response = self.client.post(
            "/manual-outcomes",
            json={
                "signal_id": "manual-api|bad",
                "result": "invalid",
            },
        )

        self.assertEqual(422, response.status_code)

    def test_trade_ticket_returns_blocked_when_readiness_not_ready(self) -> None:
        response = self.client.get("/trade-ticket")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("BLOCKED", payload["ticket_status"])
        self.assertEqual("NOT_READY", payload["readiness_status"])
        self.assertFalse(payload["allowed_now"])
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["order_placed"])

    def test_trade_ticket_returns_proposed_with_fresh_eligible_candidate(self) -> None:
        archive.append_signal(self._eligible_signal(signal_id="eligible|ticket"), log_dir=self.log_dir)

        response = self.client.get("/trade-ticket")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("PROPOSED", payload["ticket_status"])
        self.assertEqual("eligible|ticket", payload["signal_id"])
        self.assertEqual("BTCUSDT", payload["symbol"])
        self.assertEqual("long", payload["direction"])
        self.assertEqual("13m", payload["timeframe"])
        self.assertEqual(100.0, payload["entry"])
        self.assertEqual(95.0, payload["stop"])
        self.assertEqual(105.0, payload["take_profit"])
        self.assertEqual(44.0, payload["suggested_position_usd"])
        self.assertEqual(2.0, payload["suggested_leverage"])
        self.assertEqual("isolated", payload["margin_mode"])
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["order_placed"])

    def test_trade_ticket_respects_max_position_usd_cap(self) -> None:
        archive.append_signal(self._eligible_signal(signal_id="eligible|position-cap"), log_dir=self.log_dir)

        response = self.client.get("/trade-ticket?max_position_usd=12")

        self.assertEqual(200, response.status_code)
        self.assertEqual(12.0, response.json()["suggested_position_usd"])

    def test_trade_ticket_respects_max_leverage_cap(self) -> None:
        archive.append_signal(self._eligible_signal(signal_id="eligible|leverage-cap"), log_dir=self.log_dir)

        response = self.client.get("/trade-ticket?max_leverage=1")

        self.assertEqual(200, response.status_code)
        self.assertEqual(1.0, response.json()["suggested_leverage"])

    def test_trade_ticket_blocks_missing_stop_or_take_profit(self) -> None:
        archive.append_signal(
            self._eligible_signal(signal_id="missing|stop", invalidation=0.0),
            log_dir=self.log_dir,
        )

        response = self.client.get("/trade-ticket?signal_id=missing%7Cstop")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("BLOCKED", payload["ticket_status"])
        self.assertIn("missing stop", payload["blockers"])
        self.assertIn("missing take_profit", payload["blockers"])

    def test_trade_ticket_blocks_expired_candidate(self) -> None:
        archive.append_signal(
            self._eligible_signal(
                signal_id="eligible|expired-ticket",
                timestamp=(datetime.now(UTC) - timedelta(minutes=90)).isoformat(),
            ),
            log_dir=self.log_dir,
        )

        response = self.client.get("/trade-ticket?signal_id=eligible%7Cexpired-ticket")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertIn(payload["ticket_status"], {"BLOCKED", "EXPIRED"})
        self.assertIn("candidate expired by freshness gate", payload["blockers"])

    def test_trade_ticket_blocks_non_btcusdt(self) -> None:
        archive.append_signal(
            self._eligible_signal(signal_id="eligible|eth", symbol="ETHUSDT"),
            log_dir=self.log_dir,
        )

        response = self.client.get("/trade-ticket?signal_id=eligible%7Ceth")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("BLOCKED", payload["ticket_status"])
        self.assertIn("signal_id not found in current BTCUSDT live-checklist window", "; ".join(payload["blockers"]))

    def test_approve_paper_trade_ticket_records_without_order_placement(self) -> None:
        archive.append_signal(self._eligible_signal(signal_id="eligible|approve-ticket"), log_dir=self.log_dir)
        ticket = self.client.get("/trade-ticket").json()

        response = self.client.post(
            "/trade-ticket/approve-paper",
            json={
                "ticket_id": ticket["ticket_id"],
                "operator": "josue",
                "notes": "paper approval intent only",
                "ticket_snapshot": ticket,
            },
        )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("approve_paper_ticket", payload["action"])
        self.assertEqual(ticket["ticket_id"], payload["ticket"]["ticket_id"])
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["paper_execution_enabled"])
        self.assertFalse(payload["paper_order_placed"])
        self.assertTrue((self.log_dir / "trade_tickets.ndjson").exists())

    def test_trade_tickets_lists_records(self) -> None:
        archive.append_signal(self._eligible_signal(signal_id="eligible|list-ticket"), log_dir=self.log_dir)
        ticket = self.client.get("/trade-ticket").json()
        self.client.post(
            "/trade-ticket/approve-paper",
            json={"ticket_id": ticket["ticket_id"], "operator": "josue", "ticket_snapshot": ticket},
        )

        response = self.client.get("/trade-tickets")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["order_placed"])
        self.assertEqual(1, len(payload["trade_tickets"]))

    def test_execute_paper_trade_ticket_rejects_blocked_ticket(self) -> None:
        ticket = self.client.get("/trade-ticket").json()

        response = self.client.post(
            "/trade-ticket/execute-paper",
            json={
                "ticket_id": ticket["ticket_id"] or "missing-ticket",
                "operator": "josue",
                "notes": "should reject",
            },
        )

        self.assertEqual(400, response.status_code)
        self.assertFalse((self.log_dir / "paper_executions.ndjson").exists())

    def test_execute_paper_trade_ticket_creates_paper_execution_for_proposed_ticket(self) -> None:
        archive.append_signal(self._eligible_signal(signal_id="eligible|execute-ticket"), log_dir=self.log_dir)
        ticket = self.client.get("/trade-ticket").json()

        response = self.client.post(
            "/trade-ticket/execute-paper",
            json={
                "ticket_id": ticket["ticket_id"],
                "operator": "josue",
                "notes": "paper execution only",
            },
        )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("PAPER_OPEN", payload["status"])
        self.assertEqual(ticket["ticket_id"], payload["ticket_id"])
        self.assertEqual(ticket["signal_id"], payload["signal_id"])
        self.assertEqual(ticket["suggested_position_usd"], payload["position_usd"])
        self.assertEqual(ticket["suggested_leverage"], payload["leverage"])
        self.assertTrue(payload["paper_order_placed"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["live_execution_enabled"])
        self.assertTrue((self.log_dir / "paper_executions.ndjson").exists())
        self.assertTrue((self.log_dir / "trade_tickets.ndjson").exists())

    def test_paper_executions_lists_records(self) -> None:
        archive.append_signal(self._eligible_signal(signal_id="eligible|paper-list"), log_dir=self.log_dir)
        ticket = self.client.get("/trade-ticket").json()
        created = self.client.post(
            "/trade-ticket/execute-paper",
            json={"ticket_id": ticket["ticket_id"], "operator": "josue"},
        ).json()

        list_response = self.client.get("/paper-executions")
        signal_response = self.client.get("/paper-executions?signal_id=eligible%7Cpaper-list")
        status_response = self.client.get("/paper-executions?status=PAPER_OPEN")

        self.assertEqual(200, list_response.status_code)
        payload = list_response.json()
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["order_placed"])
        self.assertEqual(1, len(payload["paper_executions"]))
        self.assertEqual(created["paper_execution_id"], payload["paper_executions"][0]["paper_execution_id"])
        self.assertEqual(1, len(signal_response.json()["paper_executions"]))
        self.assertEqual(1, len(status_response.json()["paper_executions"]))

    def test_cli_execute_paper_ticket_rejects_blocked_ticket(self) -> None:
        result = run(
            [
                ".venv/bin/python",
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "execute-paper-ticket",
                "--ticket-id",
                "blocked-ticket",
            ],
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("ticket_id", result.stderr)

    def test_cli_paper_executions_displays_records(self) -> None:
        archive.append_signal(self._eligible_signal(signal_id="eligible|cli-paper-list"), log_dir=self.log_dir)
        ticket = self.client.get("/trade-ticket").json()
        self.client.post(
            "/trade-ticket/execute-paper",
            json={"ticket_id": ticket["ticket_id"], "operator": "josue"},
        )

        result = run(
            [
                ".venv/bin/python",
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "paper-executions",
            ],
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("HAMMER RADAR PAPER EXECUTIONS", result.stdout)
        self.assertIn("PAPER_OPEN", result.stdout)
        self.assertIn("paper_order_placed=True", result.stdout)

    def test_exchange_dry_run_blocks_when_trade_ticket_is_blocked(self) -> None:
        response = self.client.get("/exchange-dry-run")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertTrue(payload["dry_run"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["live_execution_enabled"])
        self.assertEqual("BLOCKED", payload["validation_status"])
        self.assertIn("ticket_status must be PROPOSED", "; ".join(payload["blockers"]))

    def test_exchange_dry_run_validates_proposed_btcusdt_long_ticket(self) -> None:
        archive.append_signal(self._eligible_signal(signal_id="eligible|dry-run-long"), log_dir=self.log_dir)

        response = self.client.get("/exchange-dry-run")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("VALID", payload["validation_status"])
        self.assertEqual("binance_futures_dry_run", payload["exchange"])
        self.assertEqual("BTCUSDT", payload["symbol"])
        self.assertEqual("BUY", payload["side"])
        self.assertEqual("LONG", payload["position_side"])
        self.assertEqual(44.0, payload["notional_usd"])
        self.assertEqual(0.44, payload["quantity"])
        self.assertEqual(0.44, payload["quantity_rounded"])
        self.assertEqual(100.0, payload["entry_price_rounded"])
        self.assertEqual(95.0, payload["stop_price_rounded"])
        self.assertEqual(105.0, payload["take_profit_price_rounded"])
        self.assertEqual(2.0, payload["leverage"])
        self.assertEqual("isolated", payload["margin_mode"])
        self.assertTrue(payload["dry_run"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["exchange_order_payload_preview"]["sent"])

    def test_exchange_dry_run_validates_proposed_btcusdt_short_ticket_if_provided(self) -> None:
        ticket = self._ticket_snapshot(direction="short")

        response = self.client.post("/exchange-dry-run/from-ticket", json={"ticket": ticket})

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("VALID", payload["validation_status"])
        self.assertEqual("SELL", payload["side"])
        self.assertEqual("SHORT", payload["position_side"])

    def test_exchange_dry_run_blocks_unknown_symbol(self) -> None:
        ticket = self._ticket_snapshot(symbol="ETHUSDT")

        response = self.client.post("/exchange-dry-run/from-ticket", json={"ticket": ticket})

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("BLOCKED", payload["validation_status"])
        self.assertIn("unknown symbol", payload["blockers"])

    def test_exchange_dry_run_blocks_notional_below_minimum(self) -> None:
        ticket = self._ticket_snapshot(suggested_position_usd=4.0)

        response = self.client.post("/exchange-dry-run/from-ticket", json={"ticket": ticket})

        self.assertEqual("BLOCKED", response.json()["validation_status"])
        self.assertIn("notional below min_notional_usd", "; ".join(response.json()["blockers"]))

    def test_exchange_dry_run_blocks_leverage_above_max(self) -> None:
        ticket = self._ticket_snapshot(suggested_leverage=4.0)

        response = self.client.post("/exchange-dry-run/from-ticket", json={"ticket": ticket})

        self.assertEqual("BLOCKED", response.json()["validation_status"])
        self.assertIn("leverage above max", "; ".join(response.json()["blockers"]))

    def test_exchange_dry_run_blocks_missing_stop(self) -> None:
        ticket = self._ticket_snapshot(stop=None)

        response = self.client.post("/exchange-dry-run/from-ticket", json={"ticket": ticket})

        self.assertEqual("BLOCKED", response.json()["validation_status"])
        self.assertIn("missing stop", response.json()["blockers"])

    def test_exchange_dry_run_blocks_missing_take_profit(self) -> None:
        ticket = self._ticket_snapshot(take_profit=None)

        response = self.client.post("/exchange-dry-run/from-ticket", json={"ticket": ticket})

        self.assertEqual("BLOCKED", response.json()["validation_status"])
        self.assertIn("missing take_profit", response.json()["blockers"])

    def test_exchange_dry_run_rounding_follows_step_and_tick_size(self) -> None:
        ticket = self._ticket_snapshot(
            entry=100.07,
            stop=95.09,
            take_profit=105.19,
            suggested_position_usd=44.0,
        )

        response = self.client.post("/exchange-dry-run/from-ticket", json={"ticket": ticket})
        payload = response.json()

        self.assertEqual(0.439, payload["quantity_rounded"])
        self.assertEqual(100.0, payload["entry_price_rounded"])
        self.assertEqual(95.0, payload["stop_price_rounded"])
        self.assertEqual(105.1, payload["take_profit_price_rounded"])

    def test_exchange_dry_run_from_ticket_validates_fixture_ticket(self) -> None:
        response = self.client.post("/exchange-dry-run/from-ticket", json={"ticket": self._ticket_snapshot()})

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("VALID", payload["validation_status"])
        self.assertTrue(payload["dry_run"])
        self.assertFalse(payload["order_placed"])

    def test_cli_exchange_dry_run_works(self) -> None:
        archive.append_signal(self._eligible_signal(signal_id="eligible|cli-dry-run"), log_dir=self.log_dir)

        result = run(
            [
                ".venv/bin/python",
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "exchange-dry-run",
            ],
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("HAMMER RADAR EXCHANGE DRY RUN", result.stdout)
        self.assertIn("validation_status: VALID", result.stdout)
        self.assertIn("dry_run: true", result.stdout)

    def test_live_safety_returns_blocked_by_default(self) -> None:
        response = self.client.get("/live-safety")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("BLOCKED", payload["live_safety_status"])
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["order_placed"])
        self.assertTrue(payload["kill_switch_active"])
        self.assertFalse(payload["allow_live_orders"])

    def test_live_safety_blocks_not_ready_ticket_and_dry_run(self) -> None:
        payload = self.client.get("/live-safety").json()

        self.assertIn("readiness_status", payload["failed_gates"])
        self.assertIn("ticket_status", payload["failed_gates"])
        self.assertIn("exchange_dry_run_valid", payload["failed_gates"])

    def test_live_safety_blocks_without_human_approval(self) -> None:
        payload = self._evaluate_live_safety(decisions=[], paper_executions=[self._paper_execution_snapshot()])

        self.assertEqual("BLOCKED", payload["live_safety_status"])
        self.assertIn("human_approval", payload["failed_gates"])

    def test_live_safety_blocks_without_paper_execution_when_required(self) -> None:
        payload = self._evaluate_live_safety(decisions=[self._approval_snapshot()], paper_executions=[])

        self.assertEqual("BLOCKED", payload["live_safety_status"])
        self.assertIn("paper_execution_first", payload["failed_gates"])

    def test_live_safety_blocks_manual_loss_today(self) -> None:
        payload = self._evaluate_live_safety(
            manual_outcomes=[{"created_at": datetime.now(UTC).isoformat(), "result": "loss", "pnl_usd": -1.0}]
        )

        self.assertIn("no_losses_today", payload["failed_gates"])

    def test_live_safety_blocks_max_daily_loss_exceeded(self) -> None:
        payload = self._evaluate_live_safety(
            manual_outcomes=[{"created_at": datetime.now(UTC).isoformat(), "result": "skipped", "pnl_usd": -5.01}]
        )

        self.assertIn("daily_loss_limit", payload["failed_gates"])

    def test_live_safety_blocks_position_above_cap(self) -> None:
        ticket = self._ticket_snapshot(suggested_position_usd=45.0)
        payload = self._evaluate_live_safety(ticket=ticket)

        self.assertIn("position_cap", payload["failed_gates"])

    def test_live_safety_blocks_leverage_above_cap(self) -> None:
        ticket = self._ticket_snapshot(suggested_leverage=4.0)
        payload = self._evaluate_live_safety(ticket=ticket)

        self.assertIn("leverage_cap", payload["failed_gates"])

    def test_live_safety_blocks_non_isolated_margin(self) -> None:
        ticket = self._ticket_snapshot(margin_mode="cross")
        payload = self._evaluate_live_safety(ticket=ticket)

        self.assertIn("isolated_margin", payload["failed_gates"])

    def test_live_safety_all_gates_passing_but_live_disabled_is_blocked(self) -> None:
        payload = self._evaluate_live_safety(config_override={"global_kill_switch": False, "allow_live_orders": True})

        self.assertEqual("BLOCKED", payload["live_safety_status"])
        self.assertIn("live_execution_enabled", payload["failed_gates"])

    def test_live_safety_all_gates_passing_with_explicit_override_would_be_allowed(self) -> None:
        payload = self._evaluate_live_safety(
            config_override={
                "live_execution_enabled": True,
                "global_kill_switch": False,
                "allow_live_orders": True,
            }
        )

        self.assertEqual("WOULD_BE_ALLOWED_IF_LIVE_ENABLED", payload["live_safety_status"])
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["order_placed"])
        self.assertEqual([], payload["failed_gates"])

    def test_live_safety_evaluate_endpoint_works_with_fixture_snapshots(self) -> None:
        response = self.client.post("/live-safety/evaluate", json=self._live_safety_request())

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("BLOCKED", payload["live_safety_status"])
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["order_placed"])

    def test_cli_live_safety_works(self) -> None:
        result = run(
            [
                ".venv/bin/python",
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "live-safety",
            ],
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("HAMMER RADAR LIVE SAFETY ENVELOPE", result.stdout)
        self.assertIn("live_safety_status: BLOCKED", result.stdout)
        self.assertIn("order_placed: false", result.stdout)

    def test_cli_inspect_trade_ticket_works(self) -> None:
        archive.append_signal(self._eligible_signal(signal_id="eligible|cli-ticket"), log_dir=self.log_dir)

        result = run(
            [
                ".venv/bin/python",
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "trade-ticket",
            ],
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("HAMMER RADAR MACHINE TRADE TICKET", result.stdout)
        self.assertIn("ticket_status: PROPOSED", result.stdout)
        self.assertIn("live_execution_enabled: false", result.stdout)

    def _evaluate_live_safety(
        self,
        *,
        readiness: dict | None = None,
        ticket: dict | None = None,
        exchange_dry_run: dict | None = None,
        decisions: list[dict] | None = None,
        paper_executions: list[dict] | None = None,
        manual_outcomes: list[dict] | None = None,
        config_override: dict | None = None,
    ) -> dict:
        response = self.client.post(
            "/live-safety/evaluate",
            json=self._live_safety_request(
                readiness=readiness,
                ticket=ticket,
                exchange_dry_run=exchange_dry_run,
                decisions=decisions,
                paper_executions=paper_executions,
                manual_outcomes=manual_outcomes,
                config_override=config_override,
            ),
        )
        self.assertEqual(200, response.status_code)
        return response.json()

    def _live_safety_request(
        self,
        *,
        readiness: dict | None = None,
        ticket: dict | None = None,
        exchange_dry_run: dict | None = None,
        decisions: list[dict] | None = None,
        paper_executions: list[dict] | None = None,
        manual_outcomes: list[dict] | None = None,
        config_override: dict | None = None,
    ) -> dict:
        ticket = ticket or self._ticket_snapshot()
        return {
            "readiness": readiness or self._readiness_snapshot(),
            "ticket": ticket,
            "exchange_dry_run": exchange_dry_run or self._exchange_dry_run_snapshot(ticket=ticket),
            "decisions": decisions if decisions is not None else [self._approval_snapshot(ticket=ticket)],
            "paper_executions": (
                paper_executions if paper_executions is not None else [self._paper_execution_snapshot(ticket=ticket)]
            ),
            "manual_outcomes": manual_outcomes if manual_outcomes is not None else [],
            "config_override": config_override or {},
        }

    @staticmethod
    def _readiness_snapshot() -> dict:
        return {
            "readiness_status": "READY",
            "allowed_now": True,
            "current_state": {
                "manual_outcomes_today": 0,
                "losses_today": 0,
                "pnl_usd_today": 0.0,
            },
        }

    @staticmethod
    def _exchange_dry_run_snapshot(*, ticket: dict | None = None, validation_status: str = "VALID") -> dict:
        ticket = ticket or ApprovalApiTestCase._ticket_snapshot()
        return {
            "validation_status": validation_status,
            "dry_run": True,
            "order_placed": False,
            "live_execution_enabled": False,
            "symbol": ticket["symbol"],
            "notional_usd": ticket["suggested_position_usd"],
            "leverage": ticket["suggested_leverage"],
            "margin_mode": ticket["margin_mode"],
        }

    @staticmethod
    def _approval_snapshot(*, ticket: dict | None = None) -> dict:
        ticket = ticket or ApprovalApiTestCase._ticket_snapshot()
        return {
            "record_id": "approval-fixture",
            "action": "approve_paper_ticket",
            "ticket": ticket,
            "operator": "josue",
        }

    @staticmethod
    def _paper_execution_snapshot(*, ticket: dict | None = None) -> dict:
        ticket = ticket or ApprovalApiTestCase._ticket_snapshot()
        return {
            "paper_execution_id": "paper-fixture",
            "ticket_id": ticket["ticket_id"],
            "signal_id": ticket["signal_id"],
            "status": "PAPER_OPEN",
            "paper_order_placed": True,
            "order_placed": False,
            "live_execution_enabled": False,
        }

    @staticmethod
    def _ticket_snapshot(
        *,
        symbol: str = "BTCUSDT",
        direction: str = "long",
        entry: float = 100.0,
        stop: float | None = 95.0,
        take_profit: float | None = 105.0,
        suggested_position_usd: float = 44.0,
        suggested_leverage: float = 2.0,
        margin_mode: str = "isolated",
        ticket_status: str = "PROPOSED",
    ) -> dict:
        return {
            "ticket_id": "tt_fixture",
            "created_at": datetime.now(UTC).isoformat(),
            "signal_id": "fixture|ticket",
            "symbol": symbol,
            "direction": direction,
            "timeframe": "13m",
            "entry": entry,
            "stop": stop,
            "take_profit": take_profit,
            "suggested_position_usd": suggested_position_usd,
            "suggested_leverage": suggested_leverage,
            "margin_mode": margin_mode,
            "ticket_status": ticket_status,
            "blockers": [],
            "live_execution_enabled": False,
            "order_placed": False,
        }

    @staticmethod
    def _eligible_signal(
        *,
        signal_id: str,
        symbol: str = "BTCUSDT",
        direction: str = "long",
        tradable: bool = True,
        reject_reason: str | None = None,
        hammer_strength: float = 100.0,
        timestamp: str | None = None,
        invalidation: float = 95.0,
        rsi_state: str = "neutral",
    ) -> SignalRecord:
        return SignalRecord(
            signal_id=signal_id,
            symbol=symbol,
            timeframe="13m",
            direction=direction,
            timestamp=timestamp or (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
            hammer_strength=hammer_strength,
            hammer_high=101.0,
            hammer_low=94.0,
            fib_50=100.5,
            fib_618=100.0,
            fib_650=99.5,
            fib_786=98.5,
            invalidation=invalidation,
            bias_timeframe="4H",
            bias_direction="bullish",
            bias_aligned=True,
            same_direction_streak=0,
            opposite_direction_streak=0,
            tradable=tradable,
            reject_reason=reject_reason,
            trend_direction="bullish",
            trend_strength_score=0.4,
            trend_lookback_candles=3,
            ema_4h_20=100.0,
            price_vs_ema_4h_pct=0.1,
            signal_close=100.0,
            rsi_value=50.0,
            rsi_state=rsi_state,
            divergence_type="bullish",
            divergence_confirmed=True,
        )


if __name__ == "__main__":
    unittest.main()
