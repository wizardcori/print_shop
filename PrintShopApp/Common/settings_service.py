"""Persistence service for PrintShopApp settings.

The UI and application shell can keep using their existing settings shape while
the INI file format is owned by this module.
"""

import configparser
import json
import os


def _read(path):
    config = configparser.ConfigParser()
    if os.path.exists(path):
        config.read(path, encoding="utf-8-sig")
    return config


def _write(path, config):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig") as stream:
        config.write(stream)


def load_hotspot_setting(path, default_ssid):
    config = _read(path)
    return config.get("Settings", "hotspot_ssid", fallback=default_ssid).strip() or default_ssid


def save_hotspot_setting(path, ssid):
    config = _read(path)
    if not config.has_section("Settings"):
        config.add_section("Settings")
    config.set("Settings", "hotspot_ssid", str(ssid))
    _write(path, config)


def load_app_settings(path, defaults):
    """Load settings using the supplied application defaults."""
    config = _read(path)
    section = config["Settings"] if config.has_section("Settings") else {}
    storage = config["Storage"] if config.has_section("Storage") else {}
    network = config["Network"] if config.has_section("Network") else {}

    def integer(name, default, minimum=None, maximum=None):
        try:
            value = int(section.get(name, default))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value)) if minimum is not None and maximum is not None else max(minimum, value) if minimum is not None else value

    def number(name, default, minimum, maximum):
        try:
            value = float(section.get(name, default))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    def boolean(name, default):
        try:
            return config.getboolean("Settings", name, fallback=default)
        except ValueError:
            return default

    def json_value(name, default):
        try:
            return json.loads(section.get(name, json.dumps(default)))
        except (TypeError, ValueError, json.JSONDecodeError):
            return default

    zones = [x.strip() for x in storage.get("zones", "") .split(",") if x.strip()] or list(defaults["zones"])
    save_tabs = [x.strip() for x in storage.get("save_tabs", "") .split(",") if x.strip()] or list(defaults["save_tabs"])
    fares = json_value("internet_fares", defaults["internet_fares"])
    if not isinstance(fares, list) or not fares:
        fares = defaults["internet_fares"]
    try:
        fares = [{'minutes': int(x['minutes']), 'price': float(x['price'])} for x in fares if int(x['minutes']) > 0 and float(x['price']) >= 0]
    except (TypeError, ValueError, KeyError):
        fares = defaults["internet_fares"]
    colors = [str(x).strip() for x in json_value("color_options", defaults["color_options"]) if str(x).strip()]
    if not colors:
        colors = list(defaults["color_options"])

    result = dict(defaults)
    result.update({
        "ssid": section.get(
            "hotspot_ssid", section.get("ssid", defaults["ssid"])
        ).strip() or defaults["ssid"],
        "hotspot_password": section.get("hotspot_password", defaults["hotspot_password"]),
        "hotspot_password_user_set": boolean("hotspot_password_user_set", False),
        "hotspot_image": section.get("hotspot_image", ""),
        "fare_dir": section.get("fare_dir", defaults["fare_dir"]),
        "max_connections": integer("max_connections", defaults["max_connections"], 1),
        "windows_hotspot_limit": integer("windows_hotspot_limit", defaults["windows_hotspot_limit"], 1, defaults["windows_hotspot_limit_max"]),
        "status_poll_interval": number("status_poll_interval", defaults["status_poll_interval"], .5, 60),
        "expiration_check_interval": integer("expiration_check_interval", defaults["expiration_check_interval"], 30, 300),
        "file_transfer_minutes": integer("file_transfer_minutes", defaults["file_transfer_minutes"], 5, 15),
        "provide_internet_for_file_transfer": boolean("provide_internet_for_file_transfer", True),
        "internet_fares": fares,
        "color_options": colors,
        "approval_sound_enabled": boolean("approval_sound_enabled", defaults["approval_sound_enabled"]),
        "approval_sounds": [section.get(f"approval_sound_{i}", defaults["approval_sounds"][i - 1]) for i in range(1, 6)],
        "qr_output_formats": {k: section.get(f"{k}_qr_output_format", defaults["qr_output_format"]) for k in ("network", "captive")},
        "qr_output_scales": {k: config.getint("Settings", f"{k}_qr_output_scale", fallback=defaults["qr_output_scale"]) for k in ("network", "captive")},
        "qr_output_dirs": {k: section.get(f"{k}_qr_output_dir", defaults["qr_output_dir"]) for k in ("network", "captive")},
        "upload_folder": storage.get("upload_folder", defaults["upload_folder"]),
        "zones": zones,
        "save_tabs": save_tabs,
        "active_main_tab": storage.get("active_main_tab", defaults["active_main_tab"]),
        "settings_active_tab": config.getint("Settings", "settings_active_tab", fallback=0),
        "internet_nic": network.get("internet_nic", ""), "internet_ip": network.get("internet_ip", ""),
        "internet_mac": network.get("internet_mac", ""),
        "hotspot_nic": network.get("hotspot_nic", ""), "hotspot_ip": network.get("hotspot_ip", ""),
        "hotspot_mac": network.get("hotspot_mac", ""),
        "hotspot_network": network.get("hotspot_network", defaults["hotspot_network"]),
        "hotspot_gateway": network.get("hotspot_gateway", defaults["hotspot_gateway"]),
        "linkshare_splitter_sizes": json_value("linkshare_splitter_sizes", [520, 260]),
        "file_receiver_splitter_sizes": json_value("file_receiver_splitter_sizes", [520, 420]),
        "main_splitter_sizes": json_value("main_splitter_sizes", [520, 420]),
        "qr_location_splitter_sizes": json_value("qr_location_splitter_sizes", [260, 520]),
        "log_print_enabled": boolean("log_print_enabled", True),
        "print_detect_enabled": boolean("print_detect_enabled", True),
        "transfer_show_completed": boolean("transfer_show_completed", True),
        "transfer_period": section.get("transfer_period", "All"),
        "transfer_start_date": section.get("transfer_start_date", ""),
        "transfer_end_date": section.get("transfer_end_date", ""),
        "startup_enabled": boolean("startup_enabled", False),
        "hotspot_validation_results": json_value("hotspot_validation_results", {}),
    })
    return result


def save_app_settings(path, settings):
    """Persist the shared application settings without feature imports."""
    config = _read(path)
    for section_name in ("Settings", "Storage", "Network"):
        if not config.has_section(section_name):
            config.add_section(section_name)
    section = config["Settings"]
    storage = config["Storage"]
    network = config["Network"]

    def set_value(target, key, value):
        if value is not None:
            target[key] = str(value)

    for key in (
        "ssid", "hotspot_password", "hotspot_image", "fare_dir",
        "max_connections", "windows_hotspot_limit", "status_poll_interval",
        "expiration_check_interval", "settings_active_tab", "startup_enabled",
        "file_transfer_minutes", "provide_internet_for_file_transfer",
        "approval_sound_enabled", "qr_output_format", "qr_output_scale",
        "transfer_show_completed", "transfer_period", "transfer_start_date",
        "transfer_end_date", "hotspot_network", "hotspot_gateway",
        "hotspot_password_user_set",
    ):
        set_value(section, key, settings.get(key))
    if settings.get("ssid") is not None:
        section["hotspot_ssid"] = str(settings["ssid"])

    for key in ("internet_fares", "color_options"):
        if key in settings:
            section[key] = json.dumps(settings[key], ensure_ascii=False)
    for name, values_key, encoder in (
        ("format", "qr_output_formats", str),
        ("scale", "qr_output_scales", str),
        ("dir", "qr_output_dirs", str),
    ):
        for qr_type, value in settings.get(values_key, {}).items():
            section[f"{qr_type}_qr_output_{name}"] = encoder(value)

    for index, sound_path in enumerate(settings.get("approval_sounds", []), start=1):
        section[f"approval_sound_{index}"] = str(sound_path or "")

    set_value(storage, "upload_folder", settings.get("upload_folder"))
    set_value(storage, "zones", ",".join(str(value) for value in settings.get("zones", [])))
    set_value(storage, "save_tabs", ",".join(str(value) for value in settings.get("save_tabs", [])))
    set_value(storage, "active_main_tab", settings.get("active_main_tab"))

    for key in ("internet_nic", "internet_ip", "internet_mac", "hotspot_nic", "hotspot_ip", "hotspot_mac"):
        set_value(network, key, settings.get(key))

    for key in (
        "linkshare_splitter_sizes", "file_receiver_splitter_sizes",
        "main_splitter_sizes", "qr_location_splitter_sizes",
        "hotspot_validation_results",
    ):
        if key in settings:
            section[key] = json.dumps(settings[key])
    _write(path, config)


def save_settings_tab_index(path, index):
    config = _read(path)
    if not config.has_section("Settings"):
        config.add_section("Settings")
    config.set("Settings", "settings_active_tab", str(max(0, int(index))))
    _write(path, config)
