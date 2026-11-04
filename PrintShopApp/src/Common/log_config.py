from Common.config import FileConfigManager, ConfigType

class LogConfig(FileConfigManager):
    """로그 포맷 및 경로 정렬 설정 관리 클래스"""
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
    }

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