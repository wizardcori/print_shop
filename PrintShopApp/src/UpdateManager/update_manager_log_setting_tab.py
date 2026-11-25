from Common.log_settings_tab import BaseLogSettingsTab
from UpdateManager.app_name import APP_NAME

class UpdateManagerSettingsTab(BaseLogSettingsTab):
    """Build Manager 전용 로그 설정 탭."""

    app_name = APP_NAME
    # 필요 시 filename 지정 (미지정 시 <app_name>.ini 사용)
    # filename = BUILD_MANAGER_INI_NAME
