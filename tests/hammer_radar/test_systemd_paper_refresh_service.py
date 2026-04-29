from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR


REPO_ROOT = Path(__file__).resolve().parents[2]
UNIT_PATH = REPO_ROOT / "ops/systemd/hammer-paper-refresh.service"
INSTALLER_PATH = REPO_ROOT / "ops/systemd/install_hammer_paper_refresh_service.sh"
README_PATH = REPO_ROOT / "ops/systemd/README_hammer_paper_refresh.md"


class SystemdPaperRefreshServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict(os.environ, {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=True)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_systemd_unit_file_exists(self) -> None:
        self.assertTrue(UNIT_PATH.exists())

    def test_unit_execstart_points_to_repo_venv_and_watch_entrypoint(self) -> None:
        unit = UNIT_PATH.read_text(encoding="utf-8")

        self.assertIn(
            "ExecStart=/home/josue/workspace/kernel/ai-agent-orchestrator-main/.venv/bin/python "
            "-m src.app.hammer_radar.operator.paper_refresh_scheduler --watch",
            unit,
        )

    def test_unit_includes_hammer_radar_log_dir(self) -> None:
        unit = UNIT_PATH.read_text(encoding="utf-8")

        self.assertIn(
            "Environment=HAMMER_RADAR_LOG_DIR=/home/josue/workspace/kernel/ai-agent-orchestrator-main/logs/hammer_radar_forward",
            unit,
        )

    def test_unit_includes_paper_only_env_defaults(self) -> None:
        unit = UNIT_PATH.read_text(encoding="utf-8")

        self.assertIn("Environment=HAMMER_REFRESH_USE_NETWORK=false", unit)
        self.assertIn("Environment=HAMMER_REFRESH_WRITE_OUTPUTS=true", unit)
        self.assertIn("Environment=HAMMER_REFRESH_SEND_NOTIFICATIONS=true", unit)
        self.assertIn("Environment=HAMMER_REFRESH_POLL_SECONDS=300", unit)

    def test_unit_does_not_contain_raw_secrets(self) -> None:
        unit = UNIT_PATH.read_text(encoding="utf-8")
        forbidden = ["TELEGRAM_BOT_TOKEN=", "BINANCE_API_SECRET=", "BINANCE_API_KEY=", "api_secret", "bot_token"]

        for token in forbidden:
            self.assertNotIn(token, unit)

    def test_install_script_exists_and_does_not_auto_start_unless_start_passed(self) -> None:
        script = INSTALLER_PATH.read_text(encoding="utf-8")

        self.assertTrue(INSTALLER_PATH.exists())
        self.assertIn("--start", script)
        self.assertIn("Not starting hammer-paper-refresh.service", script)
        self.assertIn("sudo systemctl enable hammer-paper-refresh.service", script)
        self.assertNotIn("TELEGRAM_BOT_TOKEN", script)

    def test_readme_contains_install_status_log_and_rollback_commands(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")

        self.assertIn("bash ops/systemd/install_hammer_paper_refresh_service.sh", readme)
        self.assertIn("systemctl status hammer-paper-refresh.service --no-pager", readme)
        self.assertIn("journalctl -u hammer-paper-refresh.service -n 80 --no-pager", readme)
        self.assertIn("sudo systemctl disable --now hammer-paper-refresh.service", readme)
        self.assertIn("No live orders. No ETH/alt live tickets. BTCUSDT remains the only live-readiness symbol.", readme)

    def test_paper_refresh_status_includes_service_metadata(self) -> None:
        response = self.client.get("/paper-refresh/status")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("hammer-paper-refresh.service", payload["service_name"])
        self.assertEqual("ops/systemd/hammer-paper-refresh.service", payload["suggested_systemd_unit_path"])
        self.assertIn("paper_refresh_scheduler --watch", payload["watcher_entrypoint"])

    def test_ui_contains_hammer_paper_refresh_service_text(self) -> None:
        response = self.client.get("/ui")

        self.assertEqual(200, response.status_code)
        html = response.text
        self.assertIn("hammer-paper-refresh.service", html)
        self.assertIn("Systemd service available: hammer-paper-refresh.service", html)
        self.assertIn("Use status/log commands before enabling.", html)


if __name__ == "__main__":
    unittest.main()
