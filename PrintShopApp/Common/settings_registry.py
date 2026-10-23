"""Runtime registry for feature-owned settings tabs."""

_tabs = {}


def register_settings_tab(*args, **kwargs):
    """
    지원하는 호출 형태 (인자 개수별 명확한 분기):
    1개: register_settings_tab(factory)
    2개: register_settings_tab(factory, order)
    3개: register_settings_tab(tab_id, title, factory)
    4개: register_settings_tab(tab_id, title, factory, order)
    """
    num_args = len(args)

    if num_args == 1:
        # 1개: factory만 전달 (속성 자동 추출, order 기본값 100)
        factory = args[0]
        if not callable(factory):
            raise TypeError("첫 번째 인자는 팩토리(클래스/함수)여야 합니다.")
        tab_id = getattr(factory, 'tab_id', factory.__name__)
        title = getattr(factory, 'title', tab_id)
        order = kwargs.get('order', 100)

    elif num_args == 2:
        # 2개: factory와 order 전달 (속성 자동 추출)
        factory = args[0]
        order = args[1]
        if not callable(factory):
            raise TypeError("첫 번째 인자는 팩토리(클래스/함수)여야 합니다.")
        tab_id = getattr(factory, 'tab_id', factory.__name__)
        title = getattr(factory, 'title', tab_id)

    elif num_args == 3:
        # 3개: tab_id, title, factory 전달 (order 기본값 100)
        tab_id, title, factory = args[0], args[1], args[2]
        order = kwargs.get('order', 100)

    elif num_args == 4:
        # 4개: tab_id, title, factory, order 모두 전달
        tab_id, title, factory, order = args[0], args[1], args[2], args[3]

    else:
        raise TypeError(f"register_settings_tab 함수는 1~4개의 인자만 허용합니다. (현재 인자 개수: {num_args})")

    # 탭 저장소에 등록
    _tabs[str(tab_id)] = (int(order), str(title), factory)

    
# def register_settings_tab(tab_id, title, factory, order=100):
#     """Register or replace a settings tab factory.

#     ``factory(parent)`` must return a QWidget. Re-registering the same id is
#     intentional and lets an optional feature refresh its implementation.
#     """
#     _tabs[str(tab_id)] = (int(order), str(title), factory)


def iter_settings_tabs():
    for tab_id, (order, title, factory) in sorted(_tabs.items(), key=lambda item: (item[1][0], item[0])):
        yield tab_id, title, factory
