from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.execution.binance_futures_connector import (
    DRY_RUN_ONLY,
    LIVE_ORDER_ENABLED,
    PREFLIGHT_READY_BUT_EXECUTION_DISABLED,
    PROMOTED_STRATEGY_KEY,
    REAL_ORDER_ENDPOINT,
    TEST_ORDER_ENDPOINT,
    TEST_ORDER_ONLY,
    append_connector_attempt,
    build_canonical_query,
    build_connector_status,
    build_signed_live_order_request,
    build_signed_test_order_request,
    connector_attempts_path,
    execute_live_order,
    load_connector_attempts,
    preview_payload,
    sanitize_headers,
    sanitize_signed_params,
    sign_query,
    submit_test_order,
)
from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.live_approval import append_live_approval_request
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR


class BinanceFuturesConnectorTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_connector_status_defaults_to_dry_run_only_and_blocked(self) -> None:
        payload = build_connector_status(env={}, log_dir=self.log_dir)

        self.assertEqual(DRY_RUN_ONLY, payload["connector_mode"])
        self.assertEqual("BLOCKED", payload["readiness"])
        self.assertIn("connector_mode is DRY_RUN_ONLY", payload["blockers"])
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["allow_live_orders"])
        self.assertTrue(payload["global_kill_switch"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["order_payload_created"])
        self.assertFalse(payload["signed_payload_created"])
        self.assertFalse(payload["test_order_network_enabled"])
        self.assertTrue(payload["real_live_endpoint_prepared"])
        self.assertTrue(payload["live_order_default_blocked"])
        self.assertFalse(payload["live_order_adapter_configured"])
        self.assertFalse(payload["protective_orders_supported"])

    def test_status_shows_key_presence_booleans_only_and_no_secrets(self) -> None:
        payload = build_connector_status(
            env={"BINANCE_API_KEY": "key-value", "BINANCE_API_SECRET": "secret-value"},
            log_dir=self.log_dir,
        )

        self.assertTrue(payload["api_key_present"])
        self.assertTrue(payload["api_secret_present"])
        self.assertFalse(payload["secrets_shown"])
        self.assertNotIn("key-value", str(payload))
        self.assertNotIn("secret-value", str(payload))
        self.assertTrue(payload["signing_available"])

    def test_canonical_query_and_signature_are_deterministic(self) -> None:
        params = {
            "type": "LIMIT",
            "timestamp": 1700000000000,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "quantity": "0.44",
            "price": "100",
            "timeInForce": "GTC",
            "recvWindow": 5000,
        }

        query = build_canonical_query(params)
        signature = sign_query(query, "test-secret")

        self.assertEqual(
            "price=100&quantity=0.44&recvWindow=5000&side=BUY&symbol=BTCUSDT&timeInForce=GTC&timestamp=1700000000000&type=LIMIT",
            query,
        )
        self.assertEqual("df5f40ef4f7837caaec8cc86bf84b996986bf4761fc974e3185b11f90c6dbfeb", signature)

    def test_sanitizers_hide_signature_and_api_key_header(self) -> None:
        params = sanitize_signed_params({"symbol": "BTCUSDT", "signature": "raw-signature", "api_secret": "secret"})
        headers = sanitize_headers({"X-MBX-APIKEY": "raw-key", "Content-Type": "application/x-www-form-urlencoded"})

        self.assertEqual("<hidden>", params["signature"])
        self.assertNotIn("api_secret", params)
        self.assertEqual("<present>", headers["X-MBX-APIKEY"])
        self.assertNotIn("raw-key", str(headers))

    def test_payload_preview_blocked_when_no_fresh_promoted_preflight_signal_exists(self) -> None:
        payload = preview_payload(env={}, log_dir=self.log_dir)

        self.assertEqual("BLOCKED", payload["status"])
        self.assertFalse(payload["order_payload_created"])
        self.assertIn("promoted strategy is not ready", payload["blockers"])

    def test_payload_preview_with_mocked_ready_preflight_creates_sanitized_preview_only(self) -> None:
        payload = preview_payload(preflight_pack=self._ready_pack(), env={}, log_dir=self.log_dir)
        preview = payload["payload_preview"]

        self.assertEqual("PAYLOAD_PREVIEW_CREATED", payload["status"])
        self.assertTrue(payload["order_payload_created"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["order_placed"])
        self.assertEqual("BTCUSDT", preview["symbol"])
        self.assertEqual("BUY", preview["side"])
        self.assertEqual("LONG", preview["position_side"])
        self.assertTrue(preview["preview_only"])
        self.assertFalse(preview["sent"])
        self.assertFalse(preview["signed"])
        self.assertNotIn("signature", preview)

    def test_test_order_endpoint_blocked_by_default(self) -> None:
        payload = submit_test_order(preflight_pack=self._ready_pack(), env={}, log_dir=self.log_dir)

        self.assertEqual("BLOCKED", payload["status"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["network_used"])
        self.assertFalse(payload["signed_payload_created"])
        self.assertFalse(payload["execution_attempted"])
        self.assertIn("connector_mode must be TEST_ORDER_ONLY for test-order", payload["blockers"])

    def test_test_order_blocked_when_test_mode_but_network_false_and_no_mock(self) -> None:
        env = {
            "HAMMER_BINANCE_CONNECTOR_MODE": TEST_ORDER_ONLY,
            "BINANCE_API_KEY": "key",
            "BINANCE_API_SECRET": "secret",
        }

        payload = submit_test_order(
            preflight_pack=self._ready_pack(),
            env=env,
            log_dir=self.log_dir,
            require_exact_approval=False,
        )

        self.assertEqual("BLOCKED", payload["status"])
        self.assertIn("test-order network disabled", payload["blockers"])
        self.assertFalse(payload["signed_payload_created"])
        self.assertFalse(payload["execution_attempted"])

    def test_test_order_mock_success_creates_sanitized_signed_request_and_no_order(self) -> None:
        payload = submit_test_order(
            preflight_pack=self._ready_pack(),
            env=self._test_order_env(),
            log_dir=self.log_dir,
            use_mock_adapter=True,
            require_exact_approval=False,
        )
        signed_request = payload["sanitized_signed_request"]

        self.assertEqual("TEST_ORDER_MOCK_VALIDATED", payload["status"])
        self.assertTrue(payload["signed_payload_created"])
        self.assertTrue(payload["order_payload_created"])
        self.assertTrue(payload["execution_attempted"])
        self.assertFalse(payload["network_used"])
        self.assertFalse(payload["order_placed"])
        self.assertEqual(TEST_ORDER_ENDPOINT, signed_request["endpoint"])
        self.assertEqual("<hidden>", signed_request["params"]["signature"])
        self.assertIn("timestamp", signed_request["params"])
        self.assertEqual(5000, signed_request["params"]["recvWindow"])
        self.assertEqual("<present>", signed_request["headers"]["X-MBX-APIKEY"])
        self.assertNotIn("secret-value", str(payload))
        self.assertNotIn("/fapi/v1/order\"", str(payload))

    def test_test_order_real_adapter_path_is_explicitly_enabled_and_mocked(self) -> None:
        adapter = _FakeNetworkTestOrderAdapter()

        payload = submit_test_order(
            preflight_pack=self._ready_pack(),
            env={**self._test_order_env(), "HAMMER_BINANCE_TEST_ORDER_NETWORK_ENABLED": "true"},
            log_dir=self.log_dir,
            adapter=adapter,
            require_exact_approval=False,
        )

        self.assertEqual("TEST_ORDER_SENT", payload["status"])
        self.assertTrue(payload["network_used"])
        self.assertTrue(payload["execution_attempted"])
        self.assertFalse(payload["order_placed"])
        self.assertEqual([TEST_ORDER_ENDPOINT], adapter.endpoints)

    def test_signed_request_builder_hides_secret_from_sanitized_output(self) -> None:
        preview = preview_payload(preflight_pack=self._ready_pack(), env={}, log_dir=self.log_dir, persist=False)[
            "payload_preview"
        ]
        signed = build_signed_test_order_request(
            preview,
            config={
                "base_url": "https://fapi.binance.com",
                "recv_window": 5000,
                "max_position_usd": 44.0,
                "max_leverage": 3.0,
                "margin_mode": "isolated",
            },
            source={"BINANCE_API_KEY": "key-value", "BINANCE_API_SECRET": "secret-value"},
            timestamp_ms=1700000000000,
        )
        sanitized = sanitize_signed_params(signed["params"])

        self.assertEqual(TEST_ORDER_ENDPOINT, signed["endpoint"])
        self.assertIn("signature=", signed["query_string"])
        self.assertEqual("<hidden>", sanitized["signature"])
        self.assertNotIn("secret-value", str(sanitized))

    def test_execute_endpoint_blocked_by_default(self) -> None:
        payload = execute_live_order(preflight_pack=self._ready_pack(), env={}, log_dir=self.log_dir)

        self.assertEqual("BLOCKED", payload["status"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertIn("connector_mode must be LIVE_ORDER_ENABLED", payload["blockers"])

    def test_execute_blocked_in_test_order_only(self) -> None:
        payload = execute_live_order(preflight_pack=self._ready_pack(), env=self._test_order_env(), log_dir=self.log_dir)

        self.assertEqual("BLOCKED", payload["status"])
        self.assertIn("connector_mode must be LIVE_ORDER_ENABLED", payload["blockers"])
        self.assertFalse(payload["order_placed"])

    def test_execute_blocks_live_switches_and_kill_switch_individually(self) -> None:
        cases = [
            ({"HAMMER_LIVE_EXECUTION_ENABLED": "false"}, "live_execution_enabled is false"),
            ({"HAMMER_ALLOW_LIVE_ORDERS": "false"}, "allow_live_orders is false"),
            ({"HAMMER_GLOBAL_KILL_SWITCH": "true"}, "global kill switch is active"),
        ]
        for override, blocker in cases:
            with self.subTest(blocker=blocker):
                env = dict(self._enabled_env())
                env.update(override)
                self._append_exact_approval("BTCUSDT|13m|long|ready")

                payload = execute_live_order(preflight_pack=self._ready_pack(), env=env, log_dir=self.log_dir)

                self.assertEqual("BLOCKED", payload["status"])
                self.assertIn(blocker, payload["blockers"])
                self.assertFalse(payload["order_placed"])

    def test_execute_blocks_without_exact_approval_and_wrong_signal_id(self) -> None:
        no_approval = execute_live_order(preflight_pack=self._ready_pack(), env=self._enabled_env(), log_dir=self.log_dir)
        self._append_exact_approval("BTCUSDT|13m|long|other")
        wrong_approval = execute_live_order(preflight_pack=self._ready_pack(), env=self._enabled_env(), log_dir=self.log_dir)

        self.assertIn("exact LIVE APPROVE <signal_id> is missing", no_approval["blockers"])
        self.assertIn("exact LIVE APPROVE <signal_id> is missing", wrong_approval["blockers"])
        self.assertFalse(no_approval["order_placed"])
        self.assertFalse(wrong_approval["order_placed"])

    def test_execute_blocks_requested_signal_id_mismatch(self) -> None:
        self._append_exact_approval("BTCUSDT|13m|long|ready")

        payload = execute_live_order(
            preflight_pack=self._ready_pack(),
            env=self._enabled_env(),
            log_dir=self.log_dir,
            signal_id="BTCUSDT|13m|long|other",
        )

        self.assertIn("requested signal_id does not match current preflight signal_id", payload["blockers"])
        self.assertFalse(payload["order_placed"])

    def test_execute_blocks_wrong_symbol_short_wrong_timeframe_and_risk_overrides(self) -> None:
        cases = [
            (self._ready_pack(symbol="ETHUSDT"), self._enabled_env(), "symbol must be BTCUSDT"),
            (self._ready_pack(direction="short"), self._enabled_env(), "direction must be long"),
            (self._ready_pack(timeframe="44m"), self._enabled_env(), "timeframe must be 13m"),
            (self._ready_pack(strategy_key="ETHUSDT|13m|long|ladder_close_50_618"), self._enabled_env(), "strategy_key must be BTCUSDT|13m|long|ladder_close_50_618"),
            (self._ready_pack(), {**self._enabled_env(), "HAMMER_LIVE_MAX_POSITION_USD": "45"}, "HAMMER_LIVE_MAX_POSITION_USD exceeds 44"),
            (self._ready_pack(), {**self._enabled_env(), "HAMMER_LIVE_MAX_LEVERAGE": "4"}, "HAMMER_LIVE_MAX_LEVERAGE exceeds 3"),
            (self._ready_pack(), {**self._enabled_env(), "HAMMER_LIVE_MARGIN_MODE": "cross"}, "HAMMER_LIVE_MARGIN_MODE must be isolated"),
        ]
        for pack, env, blocker in cases:
            with self.subTest(blocker=blocker):
                self._append_exact_approval(str(pack["candidate_signal_id"]))

                payload = execute_live_order(preflight_pack=pack, env=env, log_dir=self.log_dir)

                self.assertEqual("BLOCKED", payload["status"])
                self.assertIn(blocker, payload["blockers"])
                self.assertFalse(payload["order_placed"])

    def test_execute_blocks_without_fresh_promoted_preflight(self) -> None:
        payload = execute_live_order(preflight_pack={"preflight_status": "NO_PROMOTED_STRATEGY"}, env=self._enabled_env(), log_dir=self.log_dir)

        self.assertIn("promoted strategy is not ready", payload["blockers"])
        self.assertIn("no fresh promoted signal is available", payload["blockers"])
        self.assertFalse(payload["order_placed"])

    def test_execute_blocks_if_test_order_required_but_not_validated(self) -> None:
        self._append_exact_approval("BTCUSDT|13m|long|ready")

        payload = execute_live_order(
            preflight_pack=self._ready_pack(live_safety_status="PASS"),
            env=self._enabled_env(),
            log_dir=self.log_dir,
            require_protective_orders=False,
        )

        self.assertIn("successful test-order is required before live execute", payload["blockers"])
        self.assertFalse(payload["order_placed"])

    def test_execute_blocks_if_protective_order_path_not_implemented(self) -> None:
        self._append_exact_approval("BTCUSDT|13m|long|ready")
        self._append_test_order_validated("BTCUSDT|13m|long|ready")

        payload = execute_live_order(
            preflight_pack=self._ready_pack(live_safety_status="PASS"),
            env=self._enabled_env(),
            log_dir=self.log_dir,
        )

        self.assertIn("protective stop/take-profit live order path not implemented", payload["blockers"])
        self.assertFalse(payload["order_placed"])

    def test_mock_live_adapter_success_only_when_all_mocked_gates_pass(self) -> None:
        self._append_exact_approval("BTCUSDT|13m|long|ready")
        self._append_test_order_validated("BTCUSDT|13m|long|ready")

        payload = execute_live_order(
            preflight_pack=self._ready_pack(live_safety_status="PASS"),
            env=self._enabled_env(),
            log_dir=self.log_dir,
            use_mock_adapter=True,
            require_protective_orders=False,
        )

        self.assertEqual("LIVE_ORDER_MOCK_PLACED", payload["status"])
        self.assertTrue(payload["signed_payload_created"])
        self.assertTrue(payload["execution_attempted"])
        self.assertTrue(payload["order_placed"])
        self.assertTrue(payload["mock_order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["network_used"])
        self.assertEqual(REAL_ORDER_ENDPOINT, payload["sanitized_signed_request"]["endpoint"])
        self.assertEqual("<hidden>", payload["sanitized_signed_request"]["params"]["signature"])

    def test_live_signed_request_uses_real_order_endpoint_and_sanitizes(self) -> None:
        preview = preview_payload(preflight_pack=self._ready_pack(), env={}, log_dir=self.log_dir, persist=False)[
            "payload_preview"
        ]

        signed = build_signed_live_order_request(
            preview,
            signal_id="BTCUSDT|13m|long|ready",
            config={"base_url": "https://fapi.binance.com", "recv_window": 5000},
            source={"BINANCE_API_KEY": "key-value", "BINANCE_API_SECRET": "secret-value"},
            timestamp_ms=1700000000000,
        )
        sanitized = sanitize_signed_params(signed["params"])

        self.assertEqual(REAL_ORDER_ENDPOINT, signed["endpoint"])
        self.assertEqual("LIMIT", signed["params"]["type"])
        self.assertIn("newClientOrderId", signed["params"])
        self.assertEqual("<hidden>", sanitized["signature"])
        self.assertNotIn("secret-value", str(sanitized))

    def test_execute_blocks_duplicate_signal_id_and_second_live_order_today(self) -> None:
        self._append_live_sent_attempt(signal_id="BTCUSDT|13m|long|ready")
        self._append_exact_approval("BTCUSDT|13m|long|ready")

        duplicate = execute_live_order(preflight_pack=self._ready_pack(), env=self._enabled_env(), log_dir=self.log_dir)
        second_today = execute_live_order(
            preflight_pack=self._ready_pack(signal_id="BTCUSDT|13m|long|second"),
            env=self._enabled_env(),
            log_dir=self.log_dir,
        )

        self.assertIn("live order already recorded for signal_id BTCUSDT|13m|long|ready", duplicate["blockers"])
        self.assertIn("max live trades per day already reached", second_today["blockers"])
        self.assertFalse(duplicate["order_placed"])
        self.assertFalse(second_today["order_placed"])

    def test_attempts_are_persisted_and_payload_has_no_secret_or_signature(self) -> None:
        preview_payload(preflight_pack=self._ready_pack(), env={}, log_dir=self.log_dir)
        records = load_connector_attempts(limit=10, log_dir=self.log_dir)
        preview = records[0]["payload_preview"]

        self.assertEqual(1, len(records))
        self.assertTrue(connector_attempts_path(self.log_dir).exists())
        self.assertFalse(records[0]["secrets_shown"])
        self.assertFalse(preview["signed"])
        self.assertFalse(preview["signature_present"])
        self.assertNotIn("signature", preview)
        self.assertNotIn("secret", str(preview).lower())

    def test_signed_test_order_attempts_are_persisted_sanitized(self) -> None:
        submit_test_order(
            preflight_pack=self._ready_pack(),
            env=self._test_order_env(),
            log_dir=self.log_dir,
            use_mock_adapter=True,
            require_exact_approval=False,
        )
        records = load_connector_attempts(limit=10, log_dir=self.log_dir)
        record = records[0]

        self.assertEqual("TEST_ORDER_MOCK_VALIDATED", record["status"])
        self.assertTrue(record["signed_payload_created"])
        self.assertFalse(record["order_placed"])
        self.assertEqual("<hidden>", record["sanitized_signed_request"]["params"]["signature"])
        self.assertEqual("<present>", record["sanitized_signed_request"]["headers"]["X-MBX-APIKEY"])
        self.assertNotIn("secret-value", str(record))

    def test_api_endpoints_return_default_blocked_safety_flags(self) -> None:
        status = self.client.get("/binance-live/connector-status")
        preview = self.client.post("/binance-live/payload-preview", json={})
        test_order = self.client.post("/binance-live/test-order", json={})
        execute = self.client.post("/binance-live/execute", json={})
        attempts = self.client.get("/binance-live/connector-attempts")

        self.assertEqual(200, status.status_code)
        self.assertEqual(DRY_RUN_ONLY, status.json()["connector_mode"])
        self.assertFalse(status.json()["test_order_network_enabled"])
        self.assertFalse(status.json()["signing_available"])
        self.assertTrue(status.json()["real_live_endpoint_prepared"])
        self.assertTrue(status.json()["live_order_default_blocked"])
        self.assertFalse(status.json()["live_order_adapter_configured"])
        self.assertFalse(status.json()["protective_orders_supported"])
        self.assertEqual(200, preview.status_code)
        self.assertEqual("BLOCKED", preview.json()["status"])
        self.assertEqual(200, test_order.status_code)
        self.assertEqual("BLOCKED", test_order.json()["status"])
        self.assertEqual(200, execute.status_code)
        self.assertFalse(execute.json()["order_placed"])
        self.assertFalse(execute.json()["real_order_placed"])
        self.assertEqual(200, attempts.status_code)
        self.assertFalse(attempts.json()["secrets_shown"])

    def test_api_test_order_returns_safe_fields(self) -> None:
        response = self.client.post("/binance-live/test-order", json={"use_mock_adapter": True})
        payload = response.json()

        self.assertEqual(200, response.status_code)
        self.assertEqual("BLOCKED", payload["status"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["secrets_shown"])
        self.assertFalse(payload["execution_attempted"])

    def _append_exact_approval(self, signal_id: str) -> None:
        append_live_approval_request(
            {
                "request_id": f"approval-{signal_id}",
                "created_at": datetime.now(UTC).isoformat(),
                "source": "test",
                "raw_text": f"LIVE APPROVE {signal_id}",
                "normalized_action": "live_approve_exact",
                "parse_status": "ACCEPTED",
                "approval_gate_status": "READY_BUT_EXECUTION_DISABLED",
                "signal_id": signal_id,
                "order_placed": False,
                "execution_attempted": False,
                "order_payload_created": False,
            },
            log_dir=self.log_dir,
        )

    def _append_live_sent_attempt(self, *, signal_id: str) -> None:
        append_connector_attempt(
            {
                "attempt_id": "live-sent",
                "created_at": datetime.now(UTC).isoformat(),
                "endpoint": "execute",
                "action": "execute",
                "connector_mode": LIVE_ORDER_ENABLED,
                "signal_id": signal_id,
                "preflight_id": "preflight-ready",
                "status": "LIVE_ORDER_SENT",
                "blockers": [],
                "network_used": True,
                "order_payload_created": True,
                "execution_attempted": True,
                "order_placed": True,
                "real_order_placed": True,
                "mock_order_placed": False,
                "live_execution_enabled": True,
                "allow_live_orders": True,
                "global_kill_switch": False,
                "secrets_shown": False,
                "payload_preview": None,
                "exchange_response": {"order_placed": True},
            },
            log_dir=self.log_dir,
        )

    def _append_test_order_validated(self, signal_id: str) -> None:
        append_connector_attempt(
            {
                "attempt_id": f"test-order-{signal_id}",
                "created_at": datetime.now(UTC).isoformat(),
                "endpoint": "test_order",
                "action": "test_order",
                "connector_mode": TEST_ORDER_ONLY,
                "signal_id": signal_id,
                "preflight_id": "preflight-ready",
                "status": "TEST_ORDER_MOCK_VALIDATED",
                "blockers": [],
                "network_used": False,
                "order_payload_created": True,
                "signed_payload_created": True,
                "execution_attempted": True,
                "order_placed": False,
                "real_order_placed": False,
                "mock_order_placed": False,
                "live_execution_enabled": False,
                "allow_live_orders": False,
                "global_kill_switch": True,
                "secrets_shown": False,
                "payload_preview": None,
                "sanitized_signed_request": None,
                "exchange_response": {"validated": True},
            },
            log_dir=self.log_dir,
        )

    @staticmethod
    def _enabled_env() -> dict[str, str]:
        return {
            "HAMMER_BINANCE_CONNECTOR_MODE": LIVE_ORDER_ENABLED,
            "HAMMER_BINANCE_LIVE_ENABLED": "true",
            "HAMMER_LIVE_EXECUTION_ENABLED": "true",
            "HAMMER_ALLOW_LIVE_ORDERS": "true",
            "HAMMER_GLOBAL_KILL_SWITCH": "false",
            "BINANCE_API_KEY": "present",
            "BINANCE_API_SECRET": "present",
        }

    @staticmethod
    def _test_order_env() -> dict[str, str]:
        return {
            "HAMMER_BINANCE_CONNECTOR_MODE": TEST_ORDER_ONLY,
            "BINANCE_API_KEY": "key-value",
            "BINANCE_API_SECRET": "secret-value",
        }

    @staticmethod
    def _ready_pack(
        *,
        signal_id: str = "BTCUSDT|13m|long|ready",
        symbol: str = "BTCUSDT",
        timeframe: str = "13m",
        direction: str = "long",
        strategy_key: str = PROMOTED_STRATEGY_KEY,
        live_safety_status: str = "BLOCKED",
    ) -> dict:
        return {
            "preflight_id": "preflight-ready",
            "preflight_status": PREFLIGHT_READY_BUT_EXECUTION_DISABLED,
            "promoted_strategy_ready": True,
            "matching_fresh_signal_found": True,
            "strategy_key": strategy_key,
            "candidate_signal_id": signal_id,
            "signal_id": signal_id,
            "readiness_status": "READY",
            "ticket_status": "PROPOSED",
            "dry_run_status": "VALID",
            "live_safety_status": live_safety_status,
            "candidate": {
                "signal_id": signal_id,
                "symbol": symbol,
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


class _FakeNetworkTestOrderAdapter:
    def __init__(self) -> None:
        self.endpoints: list[str] = []

    def send_test_order(self, signed_request: dict) -> dict:
        self.endpoints.append(signed_request["endpoint"])
        return {
            "endpoint": signed_request["endpoint"],
            "network_used": True,
            "order_placed": False,
            "validated": True,
        }


if __name__ == "__main__":
    unittest.main()
