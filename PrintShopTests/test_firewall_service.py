"""Tests for the Hotspot client isolation firewall 3-step workflow."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
PROJECT_APP = ROOT.parent / "PrintShopApp"
sys.path.insert(0, str(PROJECT_APP))

from LinkShare.src.firewall_service import (
    apply_hotspot_firewall_rules,
    is_admin_user,
    is_hotspot_subnet_active,
    query_firewall_rule,
    WEB_ALLOW_RULE_NAME,
    SMB_BLOCK_RULE_NAME,
    SYSTEM_SMB_RULE_NAME,
)


class TestFirewallService(unittest.TestCase):
    def test_non_admin_fails_check1(self):
        """Verify non-admin execution fails at Step 1 Check 1."""
        with patch("LinkShare.src.firewall_service.is_admin_user", return_value=False):
            res = apply_hotspot_firewall_rules()
            self.assertFalse(res["success"])
            self.assertIn("check1_admin", res["step1_check"])
            self.assertFalse(res["step1_check"]["check1_admin"]["passed"])
            self.assertIn("관리자 권한", res["summary"])

    def test_hotspot_inactive_when_enforced_fails_check2(self):
        """Verify inactive hotspot fails at Step 1 Check 2 when enforce_hotspot_active=True."""
        with patch("LinkShare.src.firewall_service.is_admin_user", return_value=True), \
             patch("LinkShare.src.firewall_service.is_hotspot_subnet_active", return_value=(False, "Gateway inactive")):
            res = apply_hotspot_firewall_rules(enforce_hotspot_active=True)
            self.assertFalse(res["success"])
            self.assertIn("check2_hotspot_active", res["step1_check"])
            self.assertFalse(res["step1_check"]["check2_hotspot_active"]["passed"])
            self.assertIn("Check 2", res["summary"])

    def test_full_successful_workflow(self):
        """Verify successful [Check -> Configure -> Verify] execution with mocked PowerShell."""
        def fake_run_ps(cmd, timeout=10):
            # Simulate PowerShell success
            return 0, "SUCCESS", ""

        def fake_query_rule(rule_name):
            if rule_name == WEB_ALLOW_RULE_NAME:
                return {
                    "name": WEB_ALLOW_RULE_NAME,
                    "display_name": WEB_ALLOW_RULE_NAME,
                    "enabled": True,
                    "direction": "Inbound",
                    "action": "Allow",
                    "remote_address": "192.168.137.0/24",
                    "local_port": "5000",
                }
            if rule_name == SYSTEM_SMB_RULE_NAME:
                return {
                    "name": SYSTEM_SMB_RULE_NAME,
                    "display_name": "File and Printer Sharing (SMB-In)",
                    "enabled": True,
                    "direction": "Inbound",
                    "action": "Block",
                    "remote_address": "192.168.137.0/24",
                    "local_port": "445",
                }
            if rule_name == SMB_BLOCK_RULE_NAME:
                return {
                    "name": SMB_BLOCK_RULE_NAME,
                    "display_name": SMB_BLOCK_RULE_NAME,
                    "enabled": True,
                    "direction": "Inbound",
                    "action": "Block",
                    "remote_address": "192.168.137.0/24",
                    "local_port": "445,139",
                }
            return None

        with patch("LinkShare.src.firewall_service.is_admin_user", return_value=True), \
             patch("LinkShare.src.firewall_service.is_hotspot_subnet_active", return_value=(True, "Hotspot active")), \
             patch("LinkShare.src.firewall_service.run_powershell", side_effect=fake_run_ps), \
             patch("LinkShare.src.firewall_service.query_firewall_rule", side_effect=fake_query_rule):

            res = apply_hotspot_firewall_rules(
                web_port=5000,
                hotspot_network="192.168.137.0/24",
                hotspot_gateway="192.168.137.1",
                enforce_hotspot_active=True,
            )
            self.assertTrue(res["success"])
            self.assertTrue(res["step1_check"]["check1_admin"]["passed"])
            self.assertTrue(res["step1_check"]["check2_hotspot_active"]["passed"])
            self.assertTrue(res["step1_check"]["check3_duplicate_rules"]["passed"])
            self.assertTrue(res["step2_configure"]["config1_web_allow"]["passed"])
            self.assertTrue(res["step2_configure"]["config2_smb_block"]["passed"])
            self.assertTrue(res["step3_verify"]["verify1_web_allow"]["passed"])
            self.assertTrue(res["step3_verify"]["verify2_smb_block"]["passed"])
            self.assertIn("모두 성공적으로 적용", res["summary"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
