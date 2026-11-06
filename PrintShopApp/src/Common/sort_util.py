import re

# 1. 클래스 외부에 독립적인 순수 함수로 분리 (또는 @staticmethod 사용)
def create_natural_sort_key(item: dict) -> tuple:
    """
    [정렬 키 생성 전용 함수]
    요금 딕셔너리에서 minutes 값과 item_name을 추출하여 
    정확한 수치 비교가 가능한 정렬 키(Tuple)를 생성합니다.
    """
    minutes = item.get("minutes")
    if minutes is not None:
        try:
            return (float(minutes), 0, item.get("price", 0.0))
        except ValueError:
            pass
            
    item_name = str(item.get("item_name", ""))
    tokens = re.split(r'(\d+(?:\.\d+)?)', item_name)
    
    parsed_key = []
    for token in tokens:
        if not token:
            continue
        try:
            parsed_key.append(float(token))
        except ValueError:
            parsed_key.append(token.lower())
            
    return (0, parsed_key, item.get("price", 0.0))