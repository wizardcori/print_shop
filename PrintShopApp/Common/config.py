"""Canonical runtime data paths shared by the integrated applications."""

import os
import sys

import configparser

from Common.globals import CONFIG_ENCODING
from Common.paths import CONFIG_FILE, PRINT_MONITOR_SOUND_DIR, CONFIG_FILE, TRANSFER_REGISTRY_FILE

import configparser
import os

class ConfigManager:
    def __init__(self, config_path, encoding=CONFIG_ENCODING):
        self.config_path = config_path
        self.encoding = encoding

    def load(self, section, defaults):
        """특정 섹션의 설정을 로드합니다. (defaults의 타입을 유지합니다)"""
        config = configparser.ConfigParser()
        values = defaults.copy()
        
        try:
            config.read(self.config_path, encoding=self.encoding)
            if config.has_section(section):
                for key, default_val in defaults.items():
                    if config.has_option(section, key):
                        # 불리언 타입은 configparser 내장 메서드 활용
                        if isinstance(default_val, bool):
                            values[key] = config.getboolean(section, key)
                        elif isinstance(default_val, int):
                            values[key] = config.getint(section, key)
                        elif isinstance(default_val, float):
                            values[key] = config.getfloat(section, key)
                        else:
                            values[key] = config.get(section, key).strip()
        except (OSError, configparser.Error):
            pass
            
        return values

    def save(self, section, settings):
        """특정 섹션의 설정을 저장합니다. (0, False 등 falsy 값 정상 처리)"""
        config = configparser.ConfigParser()
        if os.path.exists(self.config_path):
            try:
                config.read(self.config_path, encoding=self.encoding)
            except configparser.Error:
                pass
            
        if not config.has_section(section):
            config.add_section(section)
            
        for key, value in settings.items():
            # None이 아닌 경우 0이나 False도 정상적으로 문자열 변환되도록 처리
            str_val = str(value) if value is not None else ''
            config.set(section, key, str_val)
            
        with open(self.config_path, 'w', encoding=self.encoding) as stream:
            config.write(stream)

    def save_settings_tab(index, config_path=CONFIG_FILE):
        config = configparser.ConfigParser()
        if os.path.exists(config_path):
            config.read(config_path, encoding=CONFIG_ENCODING)
        if not config.has_section('Settings'):
            config.add_section('Settings')
        config.set('Settings', 'settings_active_tab', str(max(0, int(index))))
        with open(config_path, 'w', encoding=CONFIG_ENCODING) as stream:
            config.write(stream)


# 설정 관리자 인스턴스 생성 (전역 또는 모듈 레벨)
config_manager = ConfigManager(config_path=CONFIG_FILE, encoding=CONFIG_ENCODING)
