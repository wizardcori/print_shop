import datetime


class InternetShareFilter:
    """
    LinkShare Wi-Fi Pass Manager의 날짜 및 탭별 필터링 상태와 로직을 관리하는 클래스
    - 숫자 인덱스가 아닌 콤보 타이틀 텍스트('Today', 'Custom' 등) 기준으로 상태 저장 및 로드
    - 'Custom'인 경우에만 구체적인 start, end 날짜 기억 및 복원
    """

    FILTER_ITEMS = [
        "Today", "Yesterday", 
        "2 days ago", "3 days ago", "4 days ago", 
        "5 days ago", "6 days ago", "7 days ago", "Custom", "All"
    ]
    CONFIG_KEY = "tab_filter_states"

    def __init__(self, manager=None, config=None):
        self.manager = manager
        self.config = config
        self.tab_filter_states = {}
        self.is_updating_ui = False

        # 설정 파일에서 기존 저장된 상태 불러오기
        if self.config:
            saved_states = self.config.get(self.CONFIG_KEY)
            if isinstance(saved_states, dict):
                self.tab_filter_states = saved_states

    def _save_states(self):
        """현재 탭별 필터 상태를 설정 파일에 영구 저장"""
        if self.config:
            self.config.set(self.CONFIG_KEY, self.tab_filter_states)

    def init_tab_states(self, tab_titles):
        """탭 초기화 및 재시작 시 상태 로드 (타이틀 기준 복원 및 상대 날짜 동적 재계산)"""
        updated = False
        today_str = datetime.date.today().strftime("%Y-%m-%d")

        for title in tab_titles:
            if title not in self.tab_filter_states:
                # 신규 탭 기본값: "Today"
                self.tab_filter_states[title] = {
                    "filter_title": "Today",
                    "start": today_str,
                    "end": today_str
                }
                updated = True
            else:
                state = self.tab_filter_states[title]
                
                # 하위 호환성 보장 (기존에 combo_index가 저장되어 있던 경우 타이틀로 변환)
                if "filter_title" not in state and "combo_index" in state:
                    idx = state["combo_index"]
                    if 0 <= idx < len(self.FILTER_ITEMS):
                        state["filter_title"] = self.FILTER_ITEMS[idx]
                    else:
                        state["filter_title"] = "Today"

                filter_title = state.get("filter_title", "Today")

                if filter_title == "Custom":
                    # Custom은 사용자가 지정했던 start, end 날짜 유지
                    pass
                elif filter_title == "All":
                    state["start"] = ""
                    state["end"] = ""
                else:
                    # Today, Yesterday 등은 실행 시점의 오늘 날짜 기준으로 재계산
                    s_date, e_date = self.calculate_dates_by_filter(filter_title)
                    state["start"] = s_date
                    state["end"] = e_date
                    updated = True

        if updated:
            self._save_states()

    def calculate_dates_by_filter(self, filter_text):
        today = datetime.date.today()
        start_date = ""
        end_date = ""

        if filter_text == "Today":
            start_date = end_date = today.strftime("%Y-%m-%d")
        elif filter_text == "Yesterday":
            d = today - datetime.timedelta(days=1)
            start_date = end_date = d.strftime("%Y-%m-%d")
        elif "days ago" in filter_text:
            try:
                days_num = int(filter_text.split()[0])
                d = today - datetime.timedelta(days=days_num)
                start_date = end_date = d.strftime("%Y-%m-%d")
            except ValueError:
                pass
        elif filter_text == "All":
            start_date = ""
            end_date = ""

        return start_date, end_date

    def handle_filter_combo_changed(self, current_tab_name, current_tab_index, combo_index, combo_text, set_date_callback=None):
        if self.is_updating_ui:
            return

        start_date, end_date = self.calculate_dates_by_filter(combo_text)

        self.is_updating_ui = True
        if combo_text != "Custom" and set_date_callback:
            set_date_callback(start_date, end_date)
        self.is_updating_ui = False

        prev_state = self.get_state(current_tab_name)
        
        # Custom 선택 시에는 기존 입력되어 있던 날짜 유지, 그 외에는 계산된 날짜 적용
        final_start = start_date if combo_text != "Custom" else prev_state.get("start", "")
        final_end = end_date if combo_text != "Custom" else prev_state.get("end", "")

        # 콤보 타이틀 기준으로 상태 저장
        self.tab_filter_states[current_tab_name] = {
            "filter_title": combo_text,
            "start": final_start,
            "end": final_end
        }
        self._save_states()

        # 리스트에서 인덱스로 시그널을 꺼내서 한 번만 emit!
        if self.manager is not None and hasattr(self.manager, 'tab_signals') and self.manager.tab_signals:        
            if 0 <= current_tab_index < len(self.manager.tab_signals):
                self.manager.tab_signals[current_tab_index].emit(final_start, final_end, combo_text)

        # if self.manager and hasattr(self.manager, 'trigger_table_update'):
        #     self.manager.trigger_table_update(current_tab_index)

    def handle_date_field_changed(self, current_tab_name, current_tab_index, start_val, end_val, set_custom_combo_callback=None):
        if self.is_updating_ui:
            return

        normalized_start = self.normalize_date_format(start_val)
        normalized_end = self.normalize_date_format(end_val)

        # 사용자가 직접 날짜를 입력하면 콤보 타이틀을 'Custom'으로 자동 전환
        if start_val.strip() or end_val.strip():
            filter_title = "Custom"
            custom_idx = self.FILTER_ITEMS.index("Custom")
            
            self.is_updating_ui = True
            if set_custom_combo_callback:
                set_custom_combo_callback(custom_idx)
            self.is_updating_ui = False
        else:
            filter_title = self.get_state(current_tab_name).get("filter_title", "Today")

        self.tab_filter_states[current_tab_name] = {
            "filter_title": filter_title,
            "start": normalized_start,
            "end": normalized_end
        }
        self._save_states()

        # 리스트에서 인덱스로 시그널을 꺼내서 한 번만 emit!
        if self.manager is not None and hasattr(self.manager, 'tab_signals') and self.manager.tab_signals:        
            if 0 <= current_tab_index < len(self.manager.tab_signals):
                self.manager.tab_signals[current_tab_index].emit(normalized_start, normalized_end, filter_title)

        # if self.manager and hasattr(self.manager, 'trigger_table_update'):
        #     self.manager.trigger_table_update(current_tab_index)

    def handle_tab_changed(self, new_tab_name, new_tab_idx, sync_ui_callback=None):
        state = self.get_state(new_tab_name)
        filter_title = state.get("filter_title", "Today")

        # 콤보 타이틀에 해당하는 인덱스 계산
        combo_idx = 0
        if filter_title in self.FILTER_ITEMS:
            combo_idx = self.FILTER_ITEMS.index(filter_title)

        self.is_updating_ui = True
        if sync_ui_callback:
            sync_ui_callback(
                combo_idx,
                state.get("start", ""),
                state.get("end", "")
            )
        self.is_updating_ui = False

        # 리스트에서 인덱스로 시그널을 꺼내서 한 번만 emit!
        if self.manager is not None and hasattr(self.manager, 'tab_signals') and self.manager.tab_signals:        
            if 0 <= new_tab_idx < len(self.manager.tab_signals):
                start = state.get("start", ""),
                end = state.get("end", "")
                self.manager.tab_signals[new_tab_idx].emit(start, end, filter_title)

        # if self.manager and hasattr(self.manager, 'trigger_table_update'):
        #     self.manager.trigger_table_update(new_tab_idx)

    def get_state(self, tab_name):
        return self.tab_filter_states.get(tab_name, {"filter_title": "Today", "start": "", "end": ""})

    def get_filter_name(self, tab_name):
        state = self.get_state(tab_name)
        return state.get("filter_title", "All")

    def apply_filter_to_tab(self, tab_obj):
        if not tab_obj or not hasattr(tab_obj, 'getTitle') or not hasattr(tab_obj, 'load_filtered'):
            return
        tab_name = tab_obj.getTitle()
        state = self.get_state(tab_name)
        filter_name = self.get_filter_name(tab_name)
        tab_obj.load_filtered(state.get("start", ""), state.get("end", ""), filter_name)

    def normalize_date_format(self, date_str):
        date_str = date_str.strip()
        if not date_str:
            return ""

        today = datetime.date.today()
        current_year = today.year
        current_month = today.month

        try:
            if len(date_str) == 8 and date_str.isdigit():
                dt = datetime.datetime.strptime(date_str, "%Y%m%d")
                return dt.strftime("%Y-%m-%d")
            elif len(date_str) == 4 and date_str.isdigit():
                full_str = f"{current_year}{date_str}"
                dt = datetime.datetime.strptime(full_str, "%Y%m%d")
                return dt.strftime("%Y-%m-%d")
            elif len(date_str) <= 2 and date_str.isdigit():
                day_num = int(date_str)
                if 1 <= day_num <= 31:
                    dt = datetime.date(current_year, current_month, day_num)
                    return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

        return date_str