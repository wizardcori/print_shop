import ast
from typing import Any

from Common.config import ConfigType, FileConfigManager


class LogConfig(FileConfigManager):
    """로그 포맷, 경로 정렬 및 모듈/레벨 동적 설정 관리 클래스"""

    section = "LogConfig"
    section_order = 21
    schema = {
        "show_time": {"default": True, "type": ConfigType.BOOLEAN},
        "show_level": {"default": True, "type": ConfigType.BOOLEAN},
        "show_dir": {"default": True, "type": ConfigType.BOOLEAN},
        "show_file": {"default": False, "type": ConfigType.BOOLEAN},
        "show_line": {"default": True, "type": ConfigType.BOOLEAN},
        "show_tag": {"default": True, "type": ConfigType.BOOLEAN},
        "enable_color_file": {"default": True, "type": ConfigType.BOOLEAN},
        "enable_global_log": {"default": True, "type": ConfigType.BOOLEAN},
        "enable_global_color_file": {"default": True, "type": ConfigType.BOOLEAN},
        "path_style": {"default": "relative", "type": ConfigType.STRING},  # 'relative', 'absolute', 'fixed'
        "fixed_width_size": {"default": 48, "type": ConfigType.INTEGER},  # 고정폭 크기
        "enable_tabular_alignment": {"default": True, "type": ConfigType.BOOLEAN},  # 테이블형 일직선 정렬
        # --- 모듈 및 레벨 동적 제어 스키마 ---
        "level_enabled": {
            "default": {
                "DEBUG": True,
                "INFO": True,
                "WARNING": True,
                "ERROR": True,
                "CRITICAL": True,
            },
            "type": ConfigType.DICT,
        },
        "module_enabled": {"default": {}, "type": ConfigType.DICT},  # 모듈/태그별 활성화 여부
        "module_min_level": {"default": {}, "type": ConfigType.DICT},  # 모듈/태그별 최소 로그 레벨
        "custom_log_levels": {"default": {}, "type": ConfigType.DICT},  # 사용자가 추가 등록한 커스텀 레벨
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sync_with_file_tag_manager(prune_missing=False)

    def sync_with_file_tag_manager(self, prune_missing: bool = False):
        """log.py에 등록된 FileTagManager 모듈 목록과 LogConfig 설정을 동기화합니다.
        - log.py에는 존재하지만 config에 없는 모듈은 추가
        - prune_missing=True일 때만 미등록 모듈 키 제거 (기본 False로 저장값 보존)
        """
        try:
            from Common.log import FileTagManager

            file_modules = FileTagManager.get_module_enabled()
            if not isinstance(file_modules, dict):
                return

            current_mod_cfg = self.str_to_dict(self.get("module_enabled"))
            if not isinstance(current_mod_cfg, dict):
                current_mod_cfg = {}

            updated = False

            for mod, is_enabled in file_modules.items():
                if mod not in current_mod_cfg:
                    current_mod_cfg[mod] = is_enabled
                    updated = True

            if prune_missing:
                keys_to_remove = [mod for mod in current_mod_cfg if mod not in file_modules]
                for mod in keys_to_remove:
                    del current_mod_cfg[mod]
                    updated = True

            if updated:
                self.set("module_enabled", current_mod_cfg)
                if hasattr(self, "save"):
                    try:
                        self.save()
                    except Exception:
                        pass
        except ImportError:
            pass

    def save_runtime_config(self, updates: dict[str, Any] | None = None) -> None:
        """프로그램 실행 중 변경된 설정을 적용하고 INI 파일에 저장합니다."""
        if isinstance(updates, dict):
            for key, value in updates.items():
                self.set(key, value)
        self.save()

    def reload_from_disk(self, prune_missing: bool = False) -> None:
        """저장된 INI 파일에서 LogConfig 값을 다시 로드합니다."""
        self.config = self._create_parser()
        self._load_and_inject()
        self.sync_with_file_tag_manager(prune_missing=prune_missing)

    def build_format_string(self) -> str:
        """설정된 요소들을 조합하여 logging 포맷 스트링 생성"""
        parts = []

        if self.get("show_time"):
            parts.append("%(asctime)s")
        if self.get("show_level"):
            parts.append("%(levelname)-8s")

        show_dir = self.get("show_dir")
        show_file = self.get("show_file")
        show_line = self.get("show_line")

        if show_dir or show_file or show_line:
            parts.append("%(fixed_path)s")

        if self.get("show_tag"):
            parts.append("[%(tag)s]")

        parts.append("%(message)s")

        return " | ".join(parts)

    @classmethod
    def str_to_dict(cls, str_data) -> dict:
        if isinstance(str_data, str):
            try:
                map_data = ast.literal_eval(str_data)
            except (ValueError, SyntaxError):
                map_data = {}
        elif isinstance(str_data, dict):
            map_data = str_data
        else:
            map_data = {}

        return map_data if isinstance(map_data, dict) else {}

    def is_level_enabled(self, level: str) -> bool:
        """로그 레벨이 활성화(True)되어 있는지 확인"""
        saved_lvl_raw = self.get("level_enabled")
        saved_lvl = self.str_to_dict(saved_lvl_raw) if isinstance(saved_lvl_raw, str) else (saved_lvl_raw or {})
        return bool(saved_lvl.get(level.upper(), False))

    def is_module_enabled(self, current_mods) -> bool:
        """전달된 모듈(태그) 중 단 하나라도 활성화(True)되어 있는지 확인"""
        if isinstance(current_mods, str):
            current_mods = [current_mods]
        elif not isinstance(current_mods, (list, tuple, set)):
            return False

        saved_mod_raw = self.get("module_enabled")
        saved_mod = self.str_to_dict(saved_mod_raw) if isinstance(saved_mod_raw, str) else (saved_mod_raw or {})
        return any(bool(saved_mod.get(m, False)) for m in current_mods)


###########################################
log_config_instance = LogConfig()
###########################################
