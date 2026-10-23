"""Tests for the 6-point hotspot verification checkpoints."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parent
PROJECT_APP = ROOT.parent / "PrintShopApp"
sys.path.insert(0, str(PROJECT_APP))

from LinkShare.src.hotspot_service import (
    check_hotspot_checkpoints,
    run_hotspot_diagnostics,
    set_hotspot_enabled,
)


class TestHotspotCheckpoints(unittest.TestCase):
    def test_check_hotspot_checkpoints_structure(self):
        """Verify that check_hotspot_checkpoints returns all 6 structured checkpoints."""
        res = check_hotspot_checkpoints(
            internet_nic={'display': 'Wi-Fi (192.168.1.3)', 'ip': '192.168.1.3'},
            hotspot_nic={'display': 'Wi-Fi (192.168.1.3)', 'ip': '192.168.1.3'},
            hotspot_network='192.168.137.0/24',
            hotspot_gateway='192.168.137.1',
        )
        self.assertIn('all_passed', res)
        self.assertIn('checkpoints', res)
        self.assertIn('summary', res)

        cps = res['checkpoints']
        # 1. 인터넷 인입용 3대 체크포인트
        self.assertIn('ingress_media_state', cps)
        self.assertIn('ingress_gateway_and_internet', cps)
        self.assertIn('ingress_sharing_source_match', cps)

        # 2. 핫스팟용 3대 체크포인트
        self.assertIn('egress_adapter_active', cps)
        self.assertIn('egress_gateway_ip_assigned', cps)
        self.assertIn('egress_client_dhcp', cps)

        for key, item in cps.items():
            self.assertIn('title', item)
            self.assertIn('passed', item)
            self.assertIn('detail', item)
            self.assertIsInstance(item['passed'], bool)

    def test_run_hotspot_diagnostics_includes_checkpoints(self):
        """Verify run_hotspot_diagnostics returns checkpoint metadata and formatted text."""
        res = run_hotspot_diagnostics(
            hotspot_nic={'display': 'Wi-Fi (192.168.1.3)', 'ip': '192.168.1.3'},
            hotspot_network='192.168.137.0/24',
            hotspot_gateway='192.168.137.1',
            internet_nic={'display': 'Wi-Fi (192.168.1.3)', 'ip': '192.168.1.3'},
        )
        self.assertIn('active', res)
        self.assertIn('text', res)
        self.assertIn('checkpoints', res)
        self.assertIn('checkpoint_summary', res)
        self.assertIn('Checkpoint Verification', res['text'])

    def test_set_hotspot_enabled_enforces_ingress_media(self):
        """Verify set_hotspot_enabled aborts if ingress adapter has media disconnected."""
        with patch('LinkShare.src.hotspot_service.check_hotspot_checkpoints') as mock_cp:
            mock_cp.return_value = {
                'all_passed': False,
                'checkpoints': {
                    'ingress_media_state': {'passed': False, 'detail': 'Media disconnected'},
                    'ingress_gateway_and_internet': {'passed': True, 'detail': 'OK'},
                    'ingress_sharing_source_match': {'passed': True, 'detail': 'OK'},
                    'egress_adapter_active': {'passed': False, 'detail': ''},
                    'egress_gateway_ip_assigned': {'passed': False, 'detail': ''},
                    'egress_client_dhcp': {'passed': False, 'detail': ''},
                },
                'summary': 'FAIL',
            }
            success, msg = set_hotspot_enabled(
                True,
                'hbwifi',
                internet_nic={'display': 'Wi-Fi (192.168.1.3)', 'ip': '192.168.1.3'},
                enforce_checkpoints=True,
            )
            self.assertFalse(success)
            self.assertIn('인터넷 인입 어댑터 연결 오류', msg)

    def test_choose_optimal_adapters_rules(self):
        """Test physical adapter selection rules 1 through 6."""
        from LinkShare.src.network_adapter_service import choose_optimal_adapters

        interfaces = [
            ("Ethernet (192.168.1.10) [MAC: 00:11:22:33:44:55]", "192.168.1.10", True, False),
            ("Wi-Fi (192.168.1.5) [MAC: 30:03:C8:7C:8C:97]", "192.168.1.5", True, True),
            ("Wi-Fi 2 (169.254.169.122) [MAC: A0:47:D7:21:A4:9D]", "169.254.169.122", False, True),
            ("Tailscale (100.67.177.118)", "100.67.177.118", True, False),
        ]

        # Case 1: Both Ethernet (wired) and Wi-Fi have internet.
        # Rule 2: Wired preferred for internet, Wi-Fi left for hotspot.
        # Rule 5: Virtual adapter Tailscale excluded.
        with patch('LinkShare.src.network_adapter_service.get_adapter_hardware_info') as mock_hw, \
             patch('LinkShare.src.network_adapter_service.check_global_internet', return_value=True):
            mock_hw.return_value = (
                {'Ethernet', 'Wi-Fi', 'Wi-Fi 2'},  # Physical set
                {'Ethernet': 'Intel Ethernet', 'Wi-Fi': 'Wi-Fi 6E', 'Wi-Fi 2': 'Realtek Wi-Fi'},
                {'Ethernet': '192.168.1.1', 'Wi-Fi': '192.168.1.1'},  # Gateways
            )
            net, hot = choose_optimal_adapters(interfaces)
            self.assertEqual(net[1], "192.168.1.10")  # Ethernet selected
            self.assertEqual(hot[1], "192.168.1.5")   # Wi-Fi selected for hotspot

        # Case 2: Only Wi-Fi has internet, Wi-Fi 2 has no internet.
        # Rule 3: The one with internet is Internet NIC, the one without is Hotspot NIC.
        with patch('LinkShare.src.network_adapter_service.get_adapter_hardware_info') as mock_hw, \
             patch('LinkShare.src.network_adapter_service.check_global_internet', return_value=True):
            mock_hw.return_value = (
                {'Wi-Fi', 'Wi-Fi 2'},
                {'Wi-Fi': 'Wi-Fi 6E', 'Wi-Fi 2': 'Realtek Wi-Fi'},
                {'Wi-Fi': '192.168.1.1'},  # Only Wi-Fi has gateway
            )
            net, hot = choose_optimal_adapters(interfaces)
            self.assertEqual(net[1], "192.168.1.5")        # Wi-Fi is Internet
            self.assertEqual(hot[1], "169.254.169.122")   # Wi-Fi 2 is Hotspot

        # Case 3: Neither has internet.
        # Rule 4: Internet NIC fails (None/empty).
        with patch('LinkShare.src.network_adapter_service.get_adapter_hardware_info') as mock_hw, \
             patch('LinkShare.src.network_adapter_service.check_global_internet', return_value=False):
            mock_hw.return_value = (
                {'Wi-Fi', 'Wi-Fi 2'},
                {'Wi-Fi': 'Wi-Fi 6E', 'Wi-Fi 2': 'Realtek Wi-Fi'},
                {},  # No gateway
            )
            net, hot = choose_optimal_adapters(interfaces)
            self.assertEqual(net[0], "")  # Internet NIC fail


if __name__ == '__main__':
    unittest.main(verbosity=2)
