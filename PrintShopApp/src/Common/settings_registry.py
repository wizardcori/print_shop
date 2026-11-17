"""Runtime registry for feature-owned settings tabs (Singleton Pattern)."""

class SettingsRegistry:
    _instance = None
    _register_count = 0  # 등록 카운터 초기화

    def __new__(cls):
        if cls._instance is not None:
            return cls._instance
        cls._instance = super(SettingsRegistry, cls).__new__(cls)
        cls._instance._tabs = {}
        cls._register_count = 0  # 등록 카운터 초기화
        return cls._instance

    def register(self, *args, **kwargs):
        """
        지원하는 호출 형태 (인자 개수별 명확한 분기):
        1개: register(factory)
        2개: register(factory, order)
        3개: register(tab_id, title, factory)
        4개: register(tab_id, title, factory, order)
        """
        from Common.log import logd, loge
        
        RED = "\033[91m"
        YELLOW = "\033[93m"
        RESET = "\033[0m"
        
        num_args = len(args)

        try:
            if num_args == 1:
                factory = args[0]
                if not callable(factory):
                    err_msg = f"[TypeError] 첫 번째 인자는 팩토리(클래스/함수)여야 합니다. 전달된 타입: {type(factory).__name__}"
                    loge(f"{RED}{err_msg}{RESET}")
                    raise TypeError(f"{RED}{err_msg}{RESET}")
                tab_id = getattr(factory, 'tab_id', getattr(factory, '__name__', str(factory)))
                title = getattr(factory, 'title', tab_id)
                order = kwargs.get('order', 100)

            elif num_args == 2:
                factory, order = args[0], args[1]
                if not callable(factory):
                    err_msg = f"[TypeError] 첫 번째 인자는 팩토리(클래스/함수)여야 합니다. 전달된 타입: {type(factory).__name__}"
                    loge(f"{RED}{err_msg}{RESET}")
                    raise TypeError(f"{RED}{err_msg}{RESET}")
                tab_id = getattr(factory, 'tab_id', getattr(factory, '__name__', str(factory)))
                title = getattr(factory, 'title', tab_id)

            elif num_args == 3:
                tab_id, title, factory = args[0], args[1], args[2]
                if not callable(factory):
                    err_msg = f"[TypeError] 세 번째 인자는 팩토리(클래스/함수)여야 합니다. 전달된 타입: {type(factory).__name__}"
                    loge(f"{RED}{err_msg}{RESET}")
                    raise TypeError(f"{RED}{err_msg}{RESET}")
                order = kwargs.get('order', 100)

            elif num_args == 4:
                tab_id, title, factory, order = args[0], args[1], args[2], args[3]
                if not callable(factory):
                    err_msg = f"[TypeError] 세 번째 인자는 팩토리(클래스/함수)여야 합니다. 전달된 타입: {type(factory).__name__}"
                    loge(f"{RED}{err_msg}{RESET}")
                    raise TypeError(f"{RED}{err_msg}{RESET}")

            else:
                err_msg = f"[TypeError] register 함수는 1~4개의 인자만 허용합니다. (현재: {num_args})"
                loge(f"{RED}{err_msg}{RESET}")
                raise TypeError(f"{RED}{err_msg}{RESET}")

            try:
                order_int = int(order)
            except (ValueError, TypeError):
                err_msg = f"[ValueError] order 값은 정수여야 합니다. 전달된 값: {order}"
                loge(f"{RED}{err_msg}{RESET}")
                raise ValueError(f"{RED}{err_msg}{RESET}")

            # tab_id 중복 검사 및 경고 로그 출력
            str_tab_id = str(tab_id)
            if str_tab_id in self._tabs:
                warn_msg = f"[Warning] 이미 등록된 tab_id입니다. 새로운 값으로 덮어씁니다: tab_id='{str_tab_id}', title='{title}', order={order_int}"
                loge(f"{YELLOW}{warn_msg}{RESET}") # 필요에 따라 경고 로그 함수(logw 등)로 변경 가능

            # 탭 저장소에 등록 (덮어쓰기)
            self._register_count += 1
            self._tabs[str_tab_id] = (order_int, str(title), factory)
            logd(f"{self._register_count:02d} : [Success] 설정 탭 등록 완료: tab_id='{str_tab_id}', title='{title}', order={order_int}")

        except (TypeError, ValueError):
            raise

    def iter_tabs(self):
        """등록된 탭 목록을 order 순서대로 정렬하여 반환합니다."""
        for tab_id, (order, title, factory) in sorted(self._tabs.items(), key=lambda item: (item[1][0], item[0])):
            yield tab_id, order, title, factory


# 모듈 레벨에서 싱글톤 인스턴스 및 헬퍼 함수 제공 (기존 코드와의 호환성 유지)
_registry_instance = SettingsRegistry()

def register_settings_tab(*args, **kwargs):
    return _registry_instance.register(*args, **kwargs)

def iter_settings_tabs():
    return _registry_instance.iter_tabs()