import re
from datetime import datetime

# 2. 날짜(YYYY-MM-DD)만 추출하여 안전하게 비교하는 필터 함수
def matches_date_filter(record, date_keys, start_text, end_text, filter_name):
    if filter_name in ('All', '전체') or (not start_text and not end_text):
        return True

    raw_date = ''
    for key in date_keys:
        val = record.get(key, '')
        if val:
            raw_date = str(val)[:10]
            break

    if not raw_date:
        return False

    try:
        target_date = datetime.strptime(raw_date, '%Y-%m-%d').date()
        start_date = datetime.strptime(start_text, '%Y-%m-%d').date() if start_text else None
        end_date = datetime.strptime(end_text, '%Y-%m-%d').date() if end_text else None

        if start_date and end_date:
            return start_date <= target_date <= end_date
        elif start_date:
            return target_date >= start_date
        elif end_date:
            return target_date <= end_date
    except ValueError:
        return False

    return True


def is_valid_date_format(date_str, fmt="%Y-%m-%d"):
    """문자열이 지정된 날짜 포맷에 맞는지 검증"""
    if not date_str or not isinstance(date_str, str):
        return False
    try:
        datetime.strptime(date_str, fmt)
        return True
    except ValueError:
        return False

def set_date_safely(date_src, obj, attr_name):
    """
    date_src가 유효한 날짜 형식이면 obj의 attr_name 속성에 값을 대입합니다.
    """
    if not date_src or not isinstance(date_src, str):
        return

    try:
        datetime.strptime(date_src, "%Y-%m-%d")
    except ValueError:
        return

    # obj 객체의 속성에 값 대입 (예: obj가 self이고 attr_name이 'start_text'면 self.start_text = date_src)
    if obj and hasattr(obj, attr_name):
        setattr(obj, attr_name, date_src)