"""Common settings persistence for the integrated shell."""
from LinkShare.src.network_adapter_service import get_nic_mac_address


def persist_settings(window, save_app_settings, runtime_settings, default_upload_folder, default_zones, default_save_tabs, default_internet_fares):
    if hasattr(window, 'linkshare_splitter'):
        window.linkshare_splitter_sizes = window.linkshare_splitter.sizes()
    if hasattr(window, 'top_splitter'):
        window.file_receiver_splitter_sizes = window.top_splitter.sizes()
    if hasattr(window, 'main_splitter'):
        window.main_splitter_sizes = window.main_splitter.sizes()
    if hasattr(window, 'qr_location_splitter'):
        window.qr_location_splitter_sizes = window.qr_location_splitter.sizes()
    if hasattr(window, 'completed_only_checkbox'):
        window.transfer_show_completed = window.completed_only_checkbox.isChecked()
    if hasattr(window, 'transfer_period_combo'):
        window.transfer_period = window.transfer_period_combo.currentText()
    transfer_start_date_value = window.transfer_start_date
    transfer_end_date_value = window.transfer_end_date
    if hasattr(window, 'transfer_start_date') and hasattr(window.transfer_start_date, 'date'):
        transfer_start_date_value = window.transfer_start_date.date().toString('yyyy-MM-dd')
    if hasattr(window, 'transfer_end_date') and hasattr(window.transfer_end_date, 'date'):
        transfer_end_date_value = window.transfer_end_date.date().toString('yyyy-MM-dd')
    save_app_settings({
        'ssid': window.hotspot_ssid,
        'hotspot_password': window.hotspot_password,
        'hotspot_password_user_set': window.hotspot_password_user_set,
        'hotspot_image': window.hotspot_image_path,
        'fare_dir': window.fare_base_dir,
        'upload_folder': default_upload_folder,
        'zones': default_zones,
        'save_tabs': default_save_tabs,
        'active_main_tab': window.get_active_main_tab_key(),
        'settings_active_tab': runtime_settings.get('settings_active_tab', 0),
        'internet_nic': window.internet_nic['display'],
        'internet_ip': window.internet_nic['ip'],
        'internet_mac': get_nic_mac_address(window.internet_nic.get('display', '')),
        'hotspot_nic': window.hotspot_nic['display'],
        'hotspot_ip': window.hotspot_nic['ip'],
        'hotspot_mac': get_nic_mac_address(window.hotspot_nic.get('display', '')),
        'hotspot_network': window.hotspot_network,
        'hotspot_gateway': window.hotspot_gateway,
        'max_connections': window.max_connections,
        'status_poll_interval': window.status_poll_interval,
        'expiration_check_interval': window.expiration_check_interval,
        'internet_fares': runtime_settings.get('internet_fares', default_internet_fares),
        'approval_sound_enabled': window.approval_sound_enabled,
        'approval_sounds': window.approval_sounds,
        'qr_output_formats': window.qr_output_formats,
        'qr_output_scales': window.qr_output_scales,
        'qr_output_dirs': window.qr_output_dirs,
        'windows_hotspot_limit': window.windows_hotspot_limit,
        'startup_enabled': window.startup_enabled,
        'file_transfer_minutes': window.file_transfer_minutes,
        'provide_internet_for_file_transfer': window.provide_internet_for_file_transfer,
        'color_options': window.color_options,
        'linkshare_splitter_sizes': window.linkshare_splitter_sizes,
        'file_receiver_splitter_sizes': window.file_receiver_splitter_sizes,
        'main_splitter_sizes': window.main_splitter_sizes,
        'qr_location_splitter_sizes': window.qr_location_splitter_sizes,
        'log_print_enabled': window.log_print_enabled,
        'print_detect_enabled': window.print_detect_enabled,
        'transfer_show_completed': window.transfer_show_completed,
        'transfer_period': window.transfer_period,
        'transfer_start_date': transfer_start_date_value,
        'transfer_end_date': transfer_end_date_value,
    })
