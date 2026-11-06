from pathlib import Path

class HtmlLoader(str):
    """
    __file__과 상대 경로를 받아 즉시 절대 경로(풀패스)로 파일을 읽고,
    문자열(str) 자체로 동작하는 HTML 로더 클래스입니다.
    """
    def __new__(cls, current_file, relative_path):
        # 1. 현재 파일의 위치를 기준으로 절대 경로 계산
        base_dir = Path(current_file).resolve().parent
        file_path = (base_dir / relative_path).resolve()
        
        try:
            # 2. 파일 읽기
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"HTML 파일을 찾을 수 없습니다. (풀패스: {file_path})")
        except Exception as e:
            raise IOError(f"파일을 읽는 중 오류가 발생했습니다: {e}")
            
        # 3. 읽은 내용을 str 객체로 변환하여 반환
        return super().__new__(cls, content)

# 객체를 생성하는 순간 html_content는 HTML 텍스트 문자열이 됩니다.
# html_content = HtmlLoader(__file__, 'portal.html')    