파이썬 개발을 위한 AI 진행 규칙 (AI_RULES.md)
1. 코드 스타일 및 표준 (Code Style & Standards)
PEP 8 준수: 모든 파이썬 코드는 공식 스타일 가이드인 PEP 8을 엄격히 준수합니다.

타입 힌팅 (Type Hinting): 함수의 매개변수와 반환값에는 반드시 타입 힌트(Type Hints)를 명시합니다 (mypy 호환).

문서화 (Docstrings): 모든 모듈, 클래스, 공개 함수에는 Google 스타일 또는 Sphinx 스타일의 Docstring을 작성하여 역할과 인자를 설명합니다.

2. 아키텍처 및 설계 원칙 (Architecture & Design)
객체지향 및 SOLID 원칙: 확장 가능하고 유지보수가 쉬운 코드를 위해 객체지향 원칙과 SOLID 디자인 원칙을 적용합니다.

관심사의 분리 (SoC): 비즈니스 로직, 데이터베이스 접근(ORM), API 라우터/컨트롤러의 역할을 명확히 분리합니다 (예: FastAPI/Django 등 프레임워크 표준 구조 준수).

하드코딩 금지: 설정 값, API 키, 비밀번호 등은 코드에 직접 작성하지 않고 환경 변수(.env, pydantic-settings 등)를 통해 관리합니다.

3. 예외 처리 및 로깅 (Error Handling & Logging)
구체적인 예외 처리: except Exception: 같은 포괄적인 예외 처리는 지양하고, 발생 가능한 구체적인 예외(ValueError, KeyError 등)를 핸들링합니다.

로깅 사용: print() 함수 대신 표준 logging 모듈을 사용하여 로그 레벨(DEBUG, INFO, WARNING, ERROR)을 관리합니다.

4. 테스트 및 품질 관리 (Testing & Quality)
테스트 코드 작성: 새로운 기능 구현이나 버그 수정 시 pytest를 활용한 단위 테스트(Unit Test) 코드를 함께 작성합니다.

의존성 관리: 패키지 관리 도구(poetry, pipenv, 또는 uv 등)를 사용하여 의존성 버전을 명확히 고정합니다.

5. AI 응답 규칙 (AI Output Rules)
전체 코드 제공: 수정 사항이 생겼을 때 일부만 보여주기보다는, 복사해서 바로 사용할 수 있도록 전체 파일 코드 또는 명확한 위치를 포함한 블록을 제공합니다.

설명 포함: 코드의 구현 의도와 핵심 로직에 대한 간결한 설명을 코드 블록 전후에 작성합니다.

보안 검토: SQL Injection, XSS, 취약한 라이브러리 사용 등 보안상 위험이 있는 코드는 사전에 차단하고 대안을 제시합니다.
