import ast
from Common.config import FileConfigManager, ConfigType

class LogConfig(FileConfigManager):
    """로그 포맷, 경로 정렬 및 모듈/레벨 동적 설정 관리 클래스"""
    section = "LogConfig"
    section_order = 21
    schema = {
        'show_time': {"default": True, "type": ConfigType.BOOLEAN},
        'show_level': {"default": True, "type": ConfigType.BOOLEAN},
        'show_dir': {"default": True, "type": ConfigType.BOOLEAN},
        'show_file': {"default": False, "type": ConfigType.BOOLEAN},
        'show_line': {"default": True, "type": ConfigType.BOOLEAN},
        'show_tag': {"default": True, "type": ConfigType.BOOLEAN},
        'enable_color_file': {"default": True, "type": ConfigType.BOOLEAN},
        'enable_global_log': {"default": True, "type": ConfigType.BOOLEAN},
        'enable_global_color_file': {"default": True, "type": ConfigType.BOOLEAN},
        'path_style': {"default": "relative", "type": ConfigType.STRING},      # 'relative', 'absolute', 'fixed'
        'fixed_width_size': {"default": 48, "type": ConfigType.INTEGER},        # 고정폭 크기
        'enable_tabular_alignment': {"default": True, "type": ConfigType.BOOLEAN}, # 테이블형 일직선 정렬
        
        # --- 모듈 및 레벨 동적 제어 스키마 ---
        'level_enabled': {
            "default": {"DEBUG": True, "INFO": True, "WARNING": True, "ERROR": True, "CRITICAL": True}, 
            "type": ConfigType.DICT
        },  # 레벨별 활성화 여부

        'module_enabled': {"default": {}, "type": ConfigType.DICT},      # 모듈/태그별 활성화 여부
        'module_min_level': {"default": {}, "type": ConfigType.DICT},    # 모듈/태그별 최소 로그 레벨
        'custom_log_levels': {"default": {}, "type": ConfigType.DICT},   # 사용자가 추가 등록한 커스텀 레벨
    }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)    
        # [추가] 로드 시점에 log.py의 FileTagManager 모듈 목록과 동기화 수행
        self.sync_with_file_tag_manager()        

    def sync_with_file_tag_manager(self):
        """log.py에 등록된 FileTagManager 모듈 목록과 LogConfig 설정을 동기화합니다.
        - log.py에는 존재하지만 config에 없는 모듈은 추가 (기본값 True 등)
        - config에는 존재하지만 log.py에 등록되지 않은 모듈은 제거
        """
        try:
            from Common.log import FileTagManager
            file_modules = FileTagManager.get_module_enabled()
            
            # 현재 config에 저장된 module_enabled 가져오기
            current_mod_cfg = self.get('module_enabled')
            current_mod_cfg = self.str_to_dict(current_mod_cfg)
            
            if not isinstance(current_mod_cfg, dict):
                current_mod_cfg = {}

            updated = False
            
            # 1. log.py(FileTagManager)에 있는 모듈 기준으로 config에 없으면 추가
            for mod, is_enabled in file_modules.items():
                if mod not in current_mod_cfg:
                    current_mod_cfg[mod] = is_enabled
                    updated = True

            # 2. config에는 있으나 log.py(FileTagManager)에 존재하지 않는 불일치 모듈은 제거
            keys_to_remove = [mod for mod in current_mod_cfg if mod not in file_modules]
            for mod in keys_to_remove:
                del current_mod_cfg[mod]
                updated = True

            # 변경 사항이 있는 경우 config에 반영 및 저장
            if updated:
                self.set('module_enabled', current_mod_cfg)
                if hasattr(self, 'save'):
                    try:
                        self.save()
                    except Exception:
                        pass
        except ImportError:
            # 순환 참조 방지 등을 위한 예외 처리
            pass        
    
    def build_format_string(self) -> str:
        """설정된 요소들을 조합하여 logging 포맷 스트링 생성"""
        parts = []

        if self.get('show_time'):
            parts.append("%(asctime)s")
        if self.get('show_level'):
            parts.append("%(levelname)-8s")

        show_dir = self.get('show_dir')
        show_file = self.get('show_file')
        show_line = self.get('show_line')

        if show_dir or show_file or show_line:
            parts.append("%(fixed_path)s")

        if self.get('show_tag'):
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

    # 만약 LogConfig 클래스 내부 메서드로 넣고 싶다면 클래스 안에 정의하고,
    # 독립된 함수로 두고 싶다면 모듈 레벨에 작성하시면 됩니다.

    def is_level_enabled(self, level: str) -> bool:
        """로그 레벨이 활성화(True)되어 있는지 확인"""
        from Common.log_config import log_config_instance
        saved_lvl_raw = log_config_instance.get('level_enabled')
        
        if isinstance(saved_lvl_raw, str):
            saved_lvl = ast.literal_eval(saved_lvl_raw)
        else:
            saved_lvl = saved_lvl_raw
            
        return saved_lvl.get(level.upper(), False)


    def is_module_enabled(self, current_mods) -> bool:
        """전달된 모듈(태그) 중 단 하나라도 활성화(True)되어 있는지 확인"""
        if isinstance(current_mods, str):
            current_mods = [current_mods]
            
        from Common.log_config import log_config_instance
        saved_mod_raw = log_config_instance.get('module_enabled')
        
        if isinstance(saved_mod_raw, str):
            saved_mod = ast.literal_eval(saved_mod_raw)
        else:
            saved_mod = saved_mod_raw
            
        # 하나라도 True인 경우가 있는지 확인
        return any(saved_mod.get(m, False) for m in current_mods)    

###########################################
log_config_instance = LogConfig()
###########################################