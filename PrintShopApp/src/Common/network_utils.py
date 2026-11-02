"""Shared network and QR helper functions."""

import ipaddress


def normalize_hotspot_network(network: str, gateway: str) -> tuple[str, str]:
    """Validate a hotspot IPv4 network and gateway, with safe defaults."""
    try:
        parsed_network = ipaddress.ip_network(network, strict=False)
        parsed_gateway = ipaddress.ip_address(gateway)
        if parsed_network.version != 4 or parsed_network.prefixlen > 30 or parsed_gateway not in parsed_network:
            raise ValueError
        return str(parsed_network), str(parsed_gateway)
    except (TypeError, ValueError):
        return '192.168.137.0/24', '192.168.137.1'


def escape_wifi_qr_field(value: str) -> str:
    """Escape a Wi-Fi QR payload field."""
    return (str(value).replace('\\', '\\\\').replace(';', '\\;')
            .replace(',', '\\,').replace(':', '\\:'))
