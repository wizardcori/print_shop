import logging
import logging.handlers
import os
import queue
import time
from datetime import datetime
import colorlog
import ast

from PySide6.QtWidgets import QWidget, QVBoxLayout, QCheckBox, QGroupBox, QLabel, QHBoxLayout, QComboBox, QSpinBox
from PySide6.QtCore import Qt

from Common.path_mgr import PathMgr
from Common.log_config import LogConfig

DEFAULT_LOG_FILE = "system.log"
DEFAULT_LOG_ALL_FILE = "log_all.log"

# ==============================================================================
# 2. Logger Classes & Infrastructure
# ==============================================================================
import os, inspect

class LogTag:
    SYSTEM = "SYSTEM"
    DATABASE = "DB"
    NETWORK = "NET"
    SECURITY = "SEC"
    USER = "USER"
    DEFAULT = "DEFAULT"

    def __init__(self, name: str):
        self.name = name.upper()

    def __str__(self):
        return self.name


class FileTagManager:
    """파일(모듈)별 기본 로그 태그 및 레벨/모듈 활성화 맵을 소유하는 관리 클래스"""
    _file_default_tags = {}
    
    _level_enabled = {
        "DEBUG": True,
        "INFO": True,
        "WARNING": True,
        "ERROR": True,
        "CRITICAL": True
    }
    
    _module_enabled = {
        "SYSTEM": True,
        "DB": True,
        "NET": True,
        "SEC": True,
        "USER": True,
        "DEFAULT": True
    }

    @classmethod
    def get_level_enabled(cls) -> dict:
        return cls._level_enabled

    @classmethod
    def get_module_enabled(cls) -> dict:
        return cls._module_enabled

    @classmethod
    def set_level_enabled(cls, level_cfg: dict):
        if isinstance(level_cfg, dict):
            cls._level_enabled.update(level_cfg)

    @classmethod
    def set_module_enabled(cls, module_cfg: dict):
        if isinstance(module_cfg, dict):
            cls._module_enabled.update(module_cfg)

    @classmethod
    def set_file_tag(cls, *tags):
        frame = inspect.currentframe().f_back
        filename = os.path.normpath(frame.f_code.co_filename)
        upper_tags = [str(t).upper() for t in tags]
        
        cls._file_default_tags[filename] = upper_tags
        
        for tag in upper_tags:
            if tag not in cls._module_enabled:
                cls._module_enabled[tag] = True

    @classmethod
    def get_current_file_mods(cls, default_tag):
        for step, f in enumerate(inspect.stack()):
            if step > 2:
                break       
            filename = os.path.normpath(f.filename)             
            if filename in cls._file_default_tags:
                return cls._file_default_tags[filename]
        
        if isinstance(default_tag, (list, tuple)):
            return [str(t).upper() for t in default_tag]
        return [str(default_tag).upper()]

set_file_tag = FileTagManager.set_file_tag


class CustomLogFormatter(logging.Formatter):
    """[노컬러 포맷터] 상대경로 및 고정폭 패딩을 적용하여 런타임 정렬 수행"""

    def format(self, record):
        if not hasattr(record, 'tag'):
            record.tag = LogTag.DEFAULT

        from Common.log_config import log_config_instance        
        log_cfg = log_config_instance
        path_style = log_cfg.get('path_style')
        fixed_width = log_cfg.get('fixed_width_size')
        do_tabular = log_cfg.get('enable_tabular_alignment')
        
        path_str = getattr(record, 'pathname', '')
        if path_style == 'relative' and path_str:
            try:
                path_str = os.path.relpath(path_str, os.getcwd())
            except Exception:
                pass
                
        lineno = getattr(record, 'lineno', '')
        loc_str = f"{path_str}:{lineno}" if lineno else path_str
        
        if do_tabular or path_style == 'fixed':
            if len(loc_str) > fixed_width:
                loc_str = "..." + loc_str[-(fixed_width-3):]
            record.fixed_path = f"{loc_str:<{fixed_width}}"
        else:
            record.fixed_path = loc_str
            
        return super().format(record)


class CustomColoredFormatter(colorlog.ColoredFormatter):
    """[컬러 포맷터] 콘솔 및 컬러 파일용 정렬 수행"""
    def format(self, record):
        if not hasattr(record, 'tag'):
            record.tag = LogTag.DEFAULT
        from Common.log_config import log_config_instance        
        log_cfg = log_config_instance
        path_style = log_cfg.get('path_style')
        fixed_width = log_cfg.get('fixed_width_size')
        do_tabular = log_cfg.get('enable_tabular_alignment')
        
        path_str = getattr(record, 'pathname', '')
        if path_style == 'relative' and path_str:
            try:
                path_str = os.path.relpath(path_str, os.getcwd())
            except Exception:
                pass
                
        lineno = getattr(record, 'lineno', '')
        loc_str = f"{path_str}:{lineno}" if lineno else path_str
        
        if do_tabular or path_style == 'fixed':
            if len(loc_str) > fixed_width:
                loc_str = "..." + loc_str[-(fixed_width-3):]
            record.fixed_path = f"{loc_str:<{fixed_width}}"
        else:
            record.fixed_path = loc_str
            
        return super().format(record)


class PeriodicFlushFileHandler(logging.FileHandler):
    def __init__(self, filename, mode='a', encoding=None, delay=False, flush_interval=5.0):
        super().__init__(filename, mode, encoding, delay)
        self.flush_interval = flush_interval
        self.last_flush_time = time.time()

    def emit(self, record):
        try:
            super().emit(record)
            current_time = time.time()
            if current_time - self.last_flush_time >= self.flush_interval:
                self.flush()
                self.last_flush_time = current_time
        except Exception:
            self.handleError(record)

    def force_flush(self):
        try:
            self.flush()
            self.last_flush_time = time.time()
        except Exception:
            pass


class LogManagerRegistry:
    """등록된 모든 로거 매니저 인스턴스를 중앙에서 관리하는 레지스트리 클래스"""
    _instances = []

    @classmethod
    def register(cls, logger_manager):
        if logger_manager not in cls._instances:
            cls._instances.append(logger_manager)

    @classmethod
    def unregister(cls, logger_manager):
        if logger_manager in cls._instances:
            cls._instances.remove(logger_manager)

    @classmethod
    def close_all_logs(cls):
        for manager in cls._instances:
            try:
                manager.close_logs()
            except Exception as e:
                print(f"로그 매니저 닫기 실패: {e}")
                
        LoggerManager.stop_all()
        if LoggerManager._global_listener:
            try:
                LoggerManager._global_listener.stop()
            except Exception:
                pass
            LoggerManager._global_listener = None
            LoggerManager._global_initialized = False

        for handler in LoggerManager._all_file_handlers:
            try:
                handler.close()
            except Exception:
                pass
        LoggerManager._all_file_handlers.clear()

    @classmethod
    def reopen_all_logs(cls):
        for manager in cls._instances:
            try:
                manager.reopen_logs()
            except Exception as e:
                print(f"로그 매니저 재시작 실패: {e}")


class LoggerManager:
    _global_queue = queue.Queue(-1)
    _global_listener = None
    _global_initialized = False
    _all_file_handlers = []
    _all_console_handlers = []
    _global_normal_handler = None
    _global_color_handler = None

    def __init__(
        self, 
        log_file=None,
        flush_interval=5.0, 
        logger_name="BaseLogger",
        individual_format=None,
        global_format=None
    ):
        self.base_log_file = log_file or os.path.join(PathMgr.LOG_DIR, DEFAULT_LOG_FILE)
        self.flush_interval = flush_interval
        self.logger_name = logger_name
        self.file_handlers = []
        self.console_handlers = []
        self.file_handler_color = None

        from Common.log_config import log_config_instance
        log_cfg = log_config_instance
        default_fmt = log_cfg.build_format_string()

        self.default_individual_format = individual_format or default_fmt
        self.default_global_format = global_format or default_fmt
        self.enable_color_file = log_cfg.get('enable_color_file')

        self._initialize_global_system()

        self.log_queue = queue.Queue(-1)
        self.listener = None
        self.logger = self._initialize_logger()

        LogManagerRegistry.register(self)

    @classmethod
    def _get_dated_file_path(cls, base_path, is_color=False):
        dir_name, file_name = os.path.split(base_path)
        name, ext = os.path.splitext(file_name)
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        if is_color:
            new_file_name = f"{name}_{today_str}_color{ext}"
        else:
            new_file_name = f"{name}_{today_str}{ext}"
            
        return os.path.join(dir_name, new_file_name) if dir_name else new_file_name

    @classmethod
    def _initialize_global_system(cls, force=False):
        if cls._global_initialized and not force:
            return

        date_format = "%Y-%m-%d %H:%M:%S"
        log_colors = {
            'DEBUG':    'cyan',
            'INFO':     'green',
            'WARNING':  'yellow',
            'ERROR':    'red',
            'CRITICAL': 'bold_red',
        }
        from Common.log_config import log_config_instance
        log_cfg = log_config_instance
        initial_global_fmt = log_cfg.build_format_string()
        enable_global = log_cfg.get('enable_global_log')
        enable_global_color = log_cfg.get('enable_global_color_file')

        if cls._global_normal_handler:
            try: cls._global_normal_handler.close()
            except Exception: pass
        if cls._global_color_handler:
            try: cls._global_color_handler.close()
            except Exception: pass
        cls._all_file_handlers.clear()

        all_target_handlers = []
        DEFAULT_LOG_ALL_FILE_PATH = os.path.join(PathMgr.LOG_DIR, DEFAULT_LOG_ALL_FILE)

        dir_name = os.path.dirname(DEFAULT_LOG_ALL_FILE_PATH)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        all_normal_path = cls._get_dated_file_path(DEFAULT_LOG_ALL_FILE_PATH, is_color=False)
        cls._global_normal_handler = PeriodicFlushFileHandler(all_normal_path, encoding="utf-8", flush_interval=5.0)
        cls._global_normal_handler.setLevel(logging.DEBUG)
        cls._global_normal_handler.setFormatter(CustomLogFormatter(initial_global_fmt, datefmt=date_format))
        if enable_global:
            all_target_handlers.append(cls._global_normal_handler)
        cls._all_file_handlers.append(cls._global_normal_handler)

        all_color_path = cls._get_dated_file_path(DEFAULT_LOG_ALL_FILE_PATH, is_color=True)
        cls._global_color_handler = PeriodicFlushFileHandler(all_color_path, encoding="utf-8", flush_interval=5.0)
        cls._global_color_handler.setLevel(logging.DEBUG)
        cls._global_color_handler.setFormatter(CustomColoredFormatter(
            "%(log_color)s" + initial_global_fmt + "%(reset)s", datefmt=date_format, log_colors=log_colors
        ))
        if enable_global and enable_global_color:
            all_target_handlers.append(cls._global_color_handler)
        cls._all_file_handlers.append(cls._global_color_handler)

        if cls._global_listener:
            try: cls._global_listener.stop()
            except Exception: pass

        cls._global_listener = logging.handlers.QueueListener(cls._global_queue, *all_target_handlers, respect_handler_level=True)
        cls._global_listener.start()
        cls._global_initialized = True

    def _initialize_logger(self):
        logger = logging.getLogger(self.logger_name)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

        if not logger.handlers:
            date_format = "%Y-%m-%d %H:%M:%S"
            log_colors = {
                'DEBUG':    'cyan',
                'INFO':     'green',
                'WARNING':  'yellow',
                'ERROR':    'red',
                'CRITICAL': 'bold_red',
            }

            target_handlers = []
            self.file_handlers.clear()
            self.console_handlers.clear()

            console_handler = colorlog.StreamHandler()
            console_handler.setLevel(logging.DEBUG)
            console_handler.setFormatter(CustomColoredFormatter(
                "%(log_color)s" + self.default_individual_format + "%(reset)s", datefmt=date_format, log_colors=log_colors
            ))
            target_handlers.append(console_handler)
            self.console_handlers.append(console_handler)

            actual_base_log_file = self.base_log_file or os.path.join(PathMgr.LOG_DIR, DEFAULT_LOG_FILE)
            dir_name = os.path.dirname(actual_base_log_file)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)

            normal_log_path = self._get_dated_file_path(actual_base_log_file, is_color=False)
            file_handler_normal = PeriodicFlushFileHandler(normal_log_path, encoding="utf-8", flush_interval=self.flush_interval)
            file_handler_normal.setLevel(logging.DEBUG)
            file_handler_normal.setFormatter(CustomLogFormatter(self.default_individual_format, datefmt=date_format))
            target_handlers.append(file_handler_normal)
            self.file_handlers.append(file_handler_normal)

            color_log_path = self._get_dated_file_path(actual_base_log_file, is_color=True)
            self.file_handler_color = PeriodicFlushFileHandler(color_log_path, encoding="utf-8", flush_interval=self.flush_interval)
            self.file_handler_color.setLevel(logging.DEBUG)
            self.file_handler_color.setFormatter(CustomColoredFormatter(
                "%(log_color)s" + self.default_individual_format + "%(reset)s", datefmt=date_format, log_colors=log_colors
            ))
            if self.enable_color_file:
                target_handlers.append(self.file_handler_color)
            self.file_handlers.append(self.file_handler_color)

            self.listener = logging.handlers.QueueListener(self.log_queue, *target_handlers, respect_handler_level=True)
            self.listener.start()

            queue_handler = logging.handlers.QueueHandler(self.log_queue)
            logger.addHandler(queue_handler)

            global_queue_handler = logging.handlers.QueueHandler(self._global_queue)
            logger.addHandler(global_queue_handler)

        return logger

    def close_logs(self):
        if self.listener:
            self.listener.stop()
            self.listener = None
            
        for handler in self.file_handlers:
            try:
                handler.close()
            except Exception:
                pass

    def reopen_logs(self):
        self.file_handlers.clear()
        
        # 바뀐 경로(PathMgr.LOG_DIR)를 반영하여 글로벌 시스템 강제 재초기화
        LoggerManager._initialize_global_system(force=True)
        
        self.logger.handlers.clear()
        
        date_format = "%Y-%m-%d %H:%M:%S"
        log_colors = {
            'DEBUG':    'cyan',
            'INFO':     'green',
            'WARNING':  'yellow',
            'ERROR':    'red',
            'CRITICAL': 'bold_red',
        }

        target_handlers = []

        console_handler = colorlog.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(CustomColoredFormatter(
            "%(log_color)s" + self.default_individual_format + "%(reset)s", datefmt=date_format, log_colors=log_colors
        ))
        target_handlers.append(console_handler)
        self.console_handlers.append(console_handler)

        actual_base_log_file = self.base_log_file or os.path.join(PathMgr.LOG_DIR, DEFAULT_LOG_FILE)
        dir_name = os.path.dirname(actual_base_log_file)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        normal_log_path = self._get_dated_file_path(actual_base_log_file, is_color=False)
        file_handler_normal = PeriodicFlushFileHandler(normal_log_path, encoding="utf-8", flush_interval=self.flush_interval)
        file_handler_normal.setLevel(logging.DEBUG)
        file_handler_normal.setFormatter(CustomLogFormatter(self.default_individual_format, datefmt=date_format))
        target_handlers.append(file_handler_normal)
        self.file_handlers.append(file_handler_normal)

        color_log_path = self._get_dated_file_path(actual_base_log_file, is_color=True)
        self.file_handler_color = PeriodicFlushFileHandler(color_log_path, encoding="utf-8", flush_interval=self.flush_interval)
        self.file_handler_color.setLevel(logging.DEBUG)
        self.file_handler_color.setFormatter(CustomColoredFormatter(
            "%(log_color)s" + self.default_individual_format + "%(reset)s", datefmt=date_format, log_colors=log_colors
        ))
        if self.enable_color_file:
            target_handlers.append(self.file_handler_color)
        self.file_handlers.append(self.file_handler_color)

        self.listener = logging.handlers.QueueListener(self.log_queue, *target_handlers, respect_handler_level=True)
        self.listener.start()

        queue_handler = logging.handlers.QueueHandler(self.log_queue)
        self.logger.addHandler(queue_handler)

        global_queue_handler = logging.handlers.QueueHandler(self._global_queue)
        self.logger.addHandler(global_queue_handler)

    def get_logger(self):
        return self.logger

    def set_individual_format(self, new_format_str: str):
        date_format = "%Y-%m-%d %H:%M:%S"
        log_colors = {'DEBUG': 'cyan', 'INFO': 'green', 'WARNING': 'yellow', 'ERROR': 'red', 'CRITICAL': 'bold_red'}
        for handler in self.console_handlers:
            handler.setFormatter(CustomColoredFormatter("%(log_color)s" + new_format_str + "%(reset)s", datefmt=date_format, log_colors=log_colors))
        for handler in self.file_handlers:
            if isinstance(handler.formatter, colorlog.ColoredFormatter):
                handler.setFormatter(CustomColoredFormatter("%(log_color)s" + new_format_str + "%(reset)s", datefmt=date_format, log_colors=log_colors))
            else:
                handler.setFormatter(CustomLogFormatter(new_format_str, datefmt=date_format))

    def update_settings(self, new_format_str: str, enable_color_file: bool):
        self.set_individual_format(new_format_str)
        self.enable_color_file = enable_color_file

        if self.listener and self.file_handler_color:
            target_handlers = [h for h in self.listener.handlers if h != self.file_handler_color]
            if self.enable_color_file:
                target_handlers.append(self.file_handler_color)
            
            self.listener.stop()
            self.listener = logging.handlers.QueueListener(self.log_queue, *target_handlers, respect_handler_level=True)
            self.listener.start()

    @classmethod
    def set_global_format(cls, new_format_str: str):
        date_format = "%Y-%m-%d %H:%M:%S"
        log_colors = {'DEBUG': 'cyan', 'INFO': 'green', 'WARNING': 'yellow', 'ERROR': 'red', 'CRITICAL': 'bold_red'}
        for handler in cls._all_file_handlers:
            if isinstance(handler.formatter, colorlog.ColoredFormatter):
                handler.setFormatter(CustomColoredFormatter("%(log_color)s" + new_format_str + "%(reset)s", datefmt=date_format, log_colors=log_colors))
            else:
                handler.setFormatter(CustomLogFormatter(new_format_str, datefmt=date_format))

    @classmethod
    def update_global_settings(cls, new_format_str: str, enable_global_log: bool, enable_global_color: bool):
        cls.set_global_format(new_format_str)
        if cls._global_listener:
            target_handlers = []
            if enable_global_log:
                if cls._global_normal_handler:
                    target_handlers.append(cls._global_normal_handler)
                if enable_global_color and cls._global_color_handler:
                    target_handlers.append(cls._global_color_handler)
            
            cls._global_listener.stop()
            cls._global_listener = logging.handlers.QueueListener(cls._global_queue, *target_handlers, respect_handler_level=True)
            cls._global_listener.start()

    def flush(self):
        while not self.log_queue.empty():
            time.sleep(0.01)
        for handler in self.file_handlers:
            if hasattr(handler, 'force_flush'): handler.force_flush()
            else: handler.flush()

        while not self._global_queue.empty():
            time.sleep(0.01)
        for handler in self._all_file_handlers:
            if hasattr(handler, 'force_flush'): handler.force_flush()
            else: handler.flush()

    @classmethod
    def stop_all(cls):
        if cls._global_listener:
            cls._global_listener.stop()

    def stop(self):
        self.flush()
        if self.listener:
            self.listener.stop()
        LogManagerRegistry.unregister(self)

    @classmethod
    def update_all_logger_formats(cls):
        from Common.log_config import log_config_instance
        new_fmt = log_config_instance.build_format_string()
        
        date_format = "%Y-%m-%d %H:%M:%S"
        log_colors = {'DEBUG': 'cyan', 'INFO': 'green', 'WARNING': 'yellow', 'ERROR': 'red', 'CRITICAL': 'bold_red'}
        
        if cls._global_normal_handler:
            cls._global_normal_handler.setFormatter(CustomLogFormatter(new_fmt, datefmt=date_format))
        if cls._global_color_handler:
            cls._global_color_handler.setFormatter(CustomColoredFormatter("%(log_color)s" + new_fmt + "%(reset)s", datefmt=date_format, log_colors=log_colors))
            
        for manager in LogManagerRegistry._instances:
            manager.set_individual_format(new_fmt)


class SubLoggerManager(LoggerManager):
    def __init__(self, log_file=None, flush_interval=5.0, module_name="SubModule", default_tag=LogTag.DEFAULT, individual_format=None, global_format=None):
        actual_log_file = log_file or os.path.join(PathMgr.LOG_DIR, DEFAULT_LOG_FILE)
        super().__init__(log_file=actual_log_file, flush_interval=flush_interval, logger_name=module_name, individual_format=individual_format, global_format=global_format)
        self.default_mod = str(default_tag)

    def _log(self, level, message: str, tag=None):
        current_tag = str(tag) if tag is not None else self.default_mod
        if level == 'debug': self.logger.debug(message, extra={'tag': current_tag}, stacklevel=3)
        elif level == 'info': self.logger.info(message, extra={'tag': current_tag}, stacklevel=3)
        elif level == 'warning': self.logger.warning(message, extra={'tag': current_tag}, stacklevel=3)
        elif level == 'error': self.logger.error(message, extra={'tag': current_tag}, stacklevel=3)
        elif level == 'critical': self.logger.critical(message, extra={'tag': current_tag}, stacklevel=3)

    def debug(self, message: str, tag=None): self._log('debug', message, tag)
    def info(self, message: str, tag=None): self._log('info', message, tag)
    def warning(self, message: str, tag=None): self._log('warning', message, tag)
    def error(self, message: str, tag=None): self._log('error', message, tag)
    def critical(self, message: str, tag=None): self._log('critical', message, tag)

    def log_database_query(self, query: str, tag=LogTag.DATABASE):
        self.info(f"Executing Query: {query}", tag=tag)

    def log_user_action(self, user_id: str, action: str, tag=LogTag.USER):
        self.warning(f"User ID: {user_id} performed '{action}'", tag=tag)


# ==============================================================================
# 3. Global Helpers & Builtins Registration
# ==============================================================================

_shared_logger = None

def setup_global_log(log_file=None, module_name="GlobalModule", default_tag=LogTag.DEFAULT):
    global _shared_logger
    if _shared_logger is None:
        actual_log_file = log_file or os.path.join(PathMgr.LOG_DIR, DEFAULT_LOG_FILE)
        os.makedirs(PathMgr.LOG_DIR, exist_ok=True)
        _shared_logger = SubLoggerManager(log_file=actual_log_file, module_name=module_name, default_tag=default_tag)
    
    import builtins
    builtins.logd = logd
    builtins.loge = loge    
    builtins.LogTag = LogTag
    builtins.set_file_tag = set_file_tag    

def reset_global_log():
    global _shared_logger
    if _shared_logger is not None:
        _shared_logger.stop()
        _shared_logger = None    

def reopen_global_log(new_log_file=None):
    reset_global_log()
    
    LoggerManager._initialize_global_system(force=True)
    
    # 등록된 개별 로거 매니저들도 재시작
    LogManagerRegistry.reopen_all_logs()
    
    # 새로운 경로로 전역 로그 재설정
    setup_global_log(log_file=new_log_file)


from Common.log_config import log_config_instance

def logd(message: str, mod=None, level="debug"):
    global _shared_logger
    if _shared_logger is None:
        setup_global_log()  

    if not log_config_instance.is_level_enabled(level):
        return

    current_mods = mod
    if not current_mods:
        current_mods = FileTagManager.get_current_file_mods(_shared_logger.default_mod)
    
    if isinstance(current_mods, str):
        current_mods = [current_mods]

    if not log_config_instance.is_module_enabled(current_mods):
        return

    mod_str = "/".join(current_mods)

    lev = level.lower()
    extra_dict = {'tag': mod_str}
    
    if lev == 'info': 
        _shared_logger.logger.info(message, extra=extra_dict, stacklevel=2)
    elif lev == 'warning': 
        _shared_logger.logger.warning(message, extra=extra_dict, stacklevel=2)
    elif lev == 'error': 
        _shared_logger.logger.error(message, extra=extra_dict, stacklevel=2)
    elif lev == 'critical': 
        _shared_logger.logger.critical(message, extra=extra_dict, stacklevel=2)
    else: 
        _shared_logger.logger.debug(message, extra=extra_dict, stacklevel=2)

def loge(message: str, tag=None, level="error"):
    global _shared_logger
    if _shared_logger is None:
        setup_global_log()  
    
    current_tags = tag
    if not current_tags:
        current_tags = FileTagManager.get_current_file_mods(_shared_logger.default_mod)
    
    if isinstance(current_tags, str):
        current_tags = [current_tags]

    tag_str = "/".join(current_tags)

    lev = level.lower()
    extra_dict = {'tag': tag_str}
    
    if lev == 'info': 
        _shared_logger.logger.info(message, extra=extra_dict, stacklevel=2)
    elif lev == 'warning': 
        _shared_logger.logger.warning(message, extra=extra_dict, stacklevel=2)
    elif lev == 'error': 
        _shared_logger.logger.error(message, extra=extra_dict, stacklevel=2)
    elif lev == 'critical': 
        _shared_logger.logger.critical(message, extra=extra_dict, stacklevel=2)
    else: 
        _shared_logger.logger.debug(message, extra=extra_dict, stacklevel=2)