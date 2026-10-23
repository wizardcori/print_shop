# 🖨️ 스마트 프린트샵 자동화 시스템 통합 기획서 (SRS) - v2.0 (네트워크 및 공유기 자동화 포함)

## 1. 시스템 개요 및 목표
- **목적:** 사용자가 다양한 기기(안드로이드, 아이폰, PC, 태블릿 등)에서 웹을 통해 파일을 전송하고 상세 규격을 설정하면, 중앙 서버와 프린터 매니저를 통해 자동으로 처리하고 출력 완료 후 후결제(후불제)를 진행하는 무인/반자동 프린트샵 시스템 구축.
- **핵심 철학:** 모든 상태는 데이터베이스 기반의 상태 머신(State Machine)으로 관리되며, 사용자와 작업자 간의 모든 조작은 양방향 실시간 웹소켓으로 동기화됨. 예외 상황 발생 시 언제든 이전 스텝으로 수동 롤백 가능.

---

## 2. 전체 시스템 아키텍처 (Architecture)

```text
[ 클라이언트 (Responsive Web - Zero-Install) ]
(안드로이드 / 아이폰 / PC / 태블릿 - QR코드 로컬 폐쇄망 접속)
│
├── (1) 파일 업로드 및 옵션 설정
├── (2) [검토 요청] ──► 서버 렌더링 (실제 출력 미리보기)
├── (3) [확정] ──► 작업자 대시보드 실시간 동기화
└── (4) 후결제 및 수령
│
▼ (WebSocket 실시간 양방향 통신 - 매장 로컬 폐쇄망)
│
[ 백엔드 서버 & 데이터베이스 (Backend & DB) ]
├── 중앙 요금표 관리 (Pricing Table)
├── 자동 검증 엔진 (Validation Engine)
└── 상태 머신 및 이력 관리 (Audit Trail)
│
▼
│
[ 프린터 서브 프로그램 (Printer Daemon) ]
├── 하드웨어 및 트레이 매핑 관리
├── 스마트 라우팅 및 로드 밸런싱 (Load Balancing)
└── 실시간 상태 모니터링 (대기중, 출력중, 완료, 에러)
```

---

## 3. 상세 프로세스 및 스텝별 워크플로우 (6단계 최적화 파이프라인)

- **[Step 1] 사용자 통합 주문 작성 및 확정 (`step1_user_order_confirmed`)**
  - **Single-Page Order Panel UX:** 파일 업로드, 옵션 설정(용지/컬러/부수/후가공), 요금표 보기, 매장 환경 실시간 검증(자동 검증 결과 표출 및 오류 시 강조 표시), 미리보기 대조 후 하단 단일 **[최종 주문 확정]** 버튼 클릭으로 주문 접수 완료.
- **[Step 2] 작업자 수동 옵션 보정 및 승인 (`step2_worker_reviewed`)**
  - 작업자 대시보드 실시간 알림 수신. 작업자가 주문 요구사항과 미리보기를 검토 및 필요시 옵션 보정/승인 수행 (필요 시 이전 스텝 롤백 가능).
- **[Step 3] 스마트 라우팅 완료 여부 (`step3_smart_routed`)**
  - 승인된 작업에 대해 스마트 라우팅 엔진이 최적의 프린터 및 트레이를 자동으로 할당.
- **[Step 4] 인쇄 대기열 할당 (`step4_print_queued`)**
  - 라우팅 결과에 따라 해당 프린터 매니저/서브 프로그램의 출력 대기열에 인쇄 작업을 할당.
- **[Step 5] 출력 실행 및 상태 추적 (`step5_printing`)**
  - 프린터 데몬이 대기열 작업을 수신하여 물리적 인쇄를 수행하며 real-time 진행 상태를 동기화.
- **[Step 6] 출력 완료 및 후결제/수령 (`step6_completed` / `step6_paid_handover`)**
  - 출력 완료 확인, 최종 정산 요금 확정, 후결제 진행 및 수령 완료 처리.

### ③ 파일별 스텝 진행 상태 표시 및 모달리스 다이얼로그 상세
- **스텝 프로그레스 및 실시간 인터랙션:**
  - 파일별 레코드 화면 테이블에 6개 통합 스텝별 컬럼(`step1_user_order_confirmed` ~ `step6_completed`)이 명시적으로 구성되어 한눈에 진행 상황 구분 가능.
  - 스텝 변경 시 웹소켓 기반 실시간 UI 업데이트 적용. 마우스/터치 호버 또는 "상세" 버튼 클릭 시 팝업/툴팁으로 세부 진행 내역 표출.
- **User 컬럼 더블클릭 모달리스(Modeless) 다이얼로그 레이아웃 구성:**
  - 작업자 대시보드/파일 목록의 'User' 컬럼 더블클릭 시 독립형 모달리스 다이얼로그 표출.
  - **좌측 UI:** 6단계 전체 진행 스텝 목록 및 스텝별 처리 상태, 타임라인 이력 관리.
  - **우측 UI:** 선택되거나 진행 중인 스텝의 상세 내용 및 실시간 미리보기 (Vector/SVG Viewer, Zoom/Pan 지원).

---

## 4. 핵심 고도화 기능 명세

### ① 자동 검증 엔진 (Automated Validation) 및 노티 이력 관리
- **검증 영역:**
  - 파일 품질 (저해상도, 폰트 깨짐, 암호 걸림, 여백 침범)
  - 옵션 적합성 (트레이 규격 불일치, 제본 한계 초과)
  - 하드웨어 상태 (용지 부족, 용지 걸림)
- **노티 및 수용 이력 관리 (`NotificationLogs`):**
  - 모든 검증 경고는 파일별/작업별로 DB에 기록 (`PENDING`).
  - 사용자 또는 작업자가 이를 **수용(`ACCEPTED`, 자동 보정 적용)**했는지, **거부(`REJECTED`, 위험 감수 강제 진행)**했는지 이력을 영구 보존하여 책임 소재 명확화.
- **장비 및 소모품 환경 관리 기능:** 매장 환경(장비 상태, 종이/소모품 재고, 트레이 구성)을 CUD(입력, 수정, 삭제) 처리할 수 있는 관리 탭 제공. 전용 DB 테이블(`StoreEnvironment`, `EquipmentConsumables`) 및 환경 설정 파일과 연동.

### ② 클라이언트 환경 전략
- **웹 기반 반응형 앱(Responsive Web / Web App) 채택:**
  - 안드로이드, 아이폰, PC, 태블릿 등 모든 기기에서 QR 스캔 한 번으로 즉시 이용 가능 (Zero-install).
  - **사용자 화면 요금표 보기 기능:** 사용자 클라이언트 UI 상단 및 옵션 영역에 "요금표 보기" 버튼 제공. 클릭 시 용지, 색상, 출력 방식, 제본/후가공 세부 단가가 명시된 요금표 팝업 표출.
  - GPU 하드웨어 가속 및 벡터(SVG) 렌더링을 적용하여 네이티브 앱과 동일한 60fps 이상의 부드러운 줌인/줌아웃 및 화면 이동 보장.

### ③ 사용자 화면 관리 탭 및 환경 설정 규격 (User Screen Settings Tab)
1. **환경 설정 내 '사용자 화면' 탭 신설 및 영속화:** 통합 환경 설정 다이얼로그(`IntegratedSettingsDialog`) 내에 **사용자 화면** 탭을 신설하고, 설정 파라미터의 영속화 저장 및 앱 재시작 시 자동 복원 기능 구현.
2. **미리보기 샘플 데이터 기초 선택 기능 (max 5):** 사용자 화면 탭에서 미리보기용 샘플 데이터 파일을 선택할 수 있는 드롭다운/목록 제공. 최대 5개(limit: max 5)까지 샘플 데이터 파일 등록 및 기초 선택 가능.
3. **Preview 체크박스 (`preview_enabled`) 제어:** Preview 체크박스 옵션 추가 (Default: 체크/True).
   - **체크 시 (`True`):** 사용자 화면(Client UI)에 실시간 Preview(미리보기) 영역이 포함된 Split-View 화면 표출.
   - **체크 해제 시 (`False`):** 미리보기 영역이 숨겨진 콤팩트 전용 주문 작성 화면 표출.
4. **윈도우 위치, Geometry 및 Splitter State 저장/복원:** 사용자 화면 탭의 윈도우 위치, 기하학적 크기(Geometry), 및 분할비(Splitter State)를 설정 파일(ini/json)에 저장하여 앱 재시작 시 이전 위치/크기/분할비 상태로 자동 복원.

### ④ 핵심 DB 테이블 구성
- **OrderFiles 테이블 명세 (통합 6단계 스텝 컬럼 체계):**
  - `step1_user_order_confirmed`: 사용자 통합 주문 작성, 설정/미리보기 검증 및 확정 상태
  - `step2_worker_reviewed`: 작업자 수동 옵션 보정 및 승인 완료 여부
  - `step3_smart_routed`: 최적 프린터/트레이 스마트 라우팅 완료 여부
  - `step4_print_queued`: 출력 대기열 할당 완료 여부
  - `step5_printing`: 출력 진행 상태 및 실시간 모니터링 이력
  - `step6_completed`: 출력 완료, 후결제 및 수령 완료 이력 (`step6_paid_handover`)

---

## 5. 네트워크 및 보안 인프라 설계 (인스토어 폐쇄망)
- **매장 공유기 세팅 및 SSID 분리:**
  - `PrintShop_Admin` (관리자 전용, 유선랜 연결, 외부 인터넷 통신 허용 - PG 결제 및 시스템 업데이트)
  - `PrintShop_Guest` (고객 전용, 외부 인터넷 원천 차단, 로컬 인쇄 서버 통신 전용)
- **AP 격리 (AP Isolation / Client Isolation):**
  - 고객용 와이파이에 접속한 스마트폰 간의 상호 통신을 원천 차단하여 해킹 및 데이터 유출 방지. 오직 고객 기기 ➔ 관리자 로컬 서버 방향의 통신만 허용.
- **방화벽 룰 설정:**
  - WAN(외부 인터넷) 방향 패킷 전면 차단 (Deny)
  - 관리자 PC 로컬 IP(`192.168.x.x:8000`) 예외 허용 (Allow)
- **고정 IP 및 QR코드 연동:**
  - 고객이 매장 내 QR코드를 스캔하면 외부 도메인이 아닌 `http://192.168.0.100:8000` (관리자 PC 로컬 주소)으로 즉시 접속되어 데이터 소모 및 외부 유출 위험 없이 고속 파일 업로드 및 미리보기 수행.

---

## 6. 공유기 설정 파이썬 자동화 및 이력 관리 모듈
관리자가 공유기 IP, 유저명, 비밀번호를 입력하면 시스템이 자동으로 설정을 검증하고 적용하는 파이썬 기반 자동화 파이프라인입니다.

### ① 자동화 단계별 프로세스
1. **연결 및 인증 확인 (Ping & Auth Check):** 공유기 IP 응답 확인 및 관리자 세션 로그인 검증. 오류 시 상세 메시지 출력.
2. **SSID 및 AP Isolation 설정:** `PrintShop_Guest` SSID 생성 및 클라이언트 격리 활성화.
3. **방화벽 룰 자동 적용:** 외부 인터넷 차단 및 관리자 포트(8000) 허용 규칙 반영.
4. **결과 재확인 (Verification):** 설정 값 재조회 후 정확히 반영되었는지 교차 검증.
5. **DB 연동 및 이력 관리 (`RouterConfigLogs`):** 설정 이력(성공/실패, 에러 메시지, 타임스탬프) 영구 기록.
6. **대시보드 조회 및 재설정 (Re-apply/Rollback):** 관리자 화면에서 과거 설정 이력 리스트를 조회하고, 필요시 원클릭으로 재설정 또는 초기화 수행.

---

## 7. 소프트웨어 전용 가상 테스트 및 장치 에뮬레이션 방안 (Pure Software Virtual Testing)
실제 프린터 및 공유기 하드웨어 장비가 없는 가상 개발/테스트 환경에서도 전체 시스템 워크플로우를 100% 검증할 수 있도록 에뮬레이션 레이어를 구축합니다.

### ① 프린터 가상 에뮬레이터 (Virtual Printer Emulator)
1. **Virtual Spooler & Dummy Printer:**
   - 가상의 IP 및 OS 드라이버 인터페이스를 제공하는 가상 프린터 스텁(Stub) 서비스 구현.
   - 물리적 출력을 대신하여 PDF/이미지 파일로 가상 생성(`output_mock/` 저장) 및 출력 속도(PPM) 가상 시뮬레이션.
2. **하드웨어 이벤트 및 에러 주입 (Fault Injection):**
   - 대시보드 및 테스트 API를 통해 Paper Jam(용지 걸림), Paper Empty(용지 고갈), Toner Low(토너 부족), Cover Open(커버 열림) 등의 에러 상태를 수동/자동으로 주입하여 시스템 노티 및 스텝 롤백 기능 동작 검증.

### ② 공유기 가상 에뮬레이터 (Virtual Router Mock Server)
1. **Mock HTTP/Router API Server:**
   - 가상의 ipTIME/ASUS 공유기 웹 인터페이스 및 API를 에뮬레이션하는 Mock 서버 구동.
   - 파이썬 자동화 모듈이 Mock 서버로 접속하여 Ping 테스트, 로그인 인증, `PrintShop_Guest` SSID 생성, AP Isolation 활성화, 방화벽 룰 적용 등의 요청을 보내고 정상/오류 응답을 확인.
2. **네트워크 예외 상황 에뮬레이션:**
   - 잘못된 비밀번호 입력, 타임아웃, 방화벽 설정 실패 등의 에러 케이스를 가상 생성하여 에러 처리 및 DB 이력(`RouterConfigLogs`) 기록 테스트.

### ③ 가상 환경 모드 전환 (Environment Switch)
1. 환경 변수(`ENV_MODE=MOCK` vs `ENV_MODE=PRODUCTION`) 설정을 통해 실제 장비 없이 소프트웨어 단독으로 모든 UI, 양방향 실시간 동기화, 자동 검증 엔진, 결제 수령 워크플로우를 테스트 가능.

---

## 8. 핫스팟 및 네트워크 연결 검증 규격 (Hotspot & Network Pre-flight Checkpoints)
핫스팟 활성화 및 진단 시 네트워크 무결성을 보장하기 위해 아래 2개 영역의 6단계 체크포인트를 검증한다.

### 8.1. 인터넷 인입용 체크포인트 (인터넷 소스 어댑터)
외부 공유기나 상위 네트워크로부터 인터넷 신호를 정상적으로 받아오고 있는지 확인하는 단계:
1. **연결 상태 확인 (Media State):**
   - [ ] `ipconfig` 및 네트워크 어댑터 상태에서 해당 인입 어댑터(예: Wi-Fi, Ethernet)가 `Media disconnected`가 아닌 상태이며, 유효한 정상 IPv4 주소(APIPA `169.254.x.x` 제외)를 할당받고 있는지 검증.
2. **게이트웨이 및 인터넷 통신 확인:**
   - [ ] 상위 공유기의 게이트웨이 주소(예: `192.168.1.1`)와 정상 통신(ICMP Ping 또는 TCP Port 80/443/53)이 가능한지, 공용 DNS/인터넷(예: `1.1.1.1`, `8.8.8.8`)과 실제로 인터넷 통신이 원활한지 검증.
3. **윈도우 모바일 핫스팟 공유 소스 매칭:**
   - [ ] Windows 설정 [모바일 핫스팟] 메뉴의 "다음에서 인터넷 연결 공유" 항목(`PreferredPublicInterface`)이 프로그램에서 지정한 인입용 어댑터와 정확히 매칭되어 있는지 검증.

### 8.2. 핫스팟용 체크포인트 (와이파이 송출 어댑터)
다른 기기(스마트폰, 노트북, 태블릿 등)로 Wi-Fi 신호와 IP를 원활하게 송출하고 있는지 확인하는 단계:
1. **핫스팟 어댑터 활성화 여부:**
   - [ ] 핫스팟 기능을 '켬(ON)'으로 전환했을 때, 가상 어댑터(예: Microsoft Wi-Fi Direct Virtual Adapter, Local Area Connection* 12/13) 또는 송출용 무선 랜카드가 UP 상태로 활성화되는지 검증.
2. **고정 IP (`192.168.137.1`) 할당 여부:**
   - [ ] 핫스팟 송출 어댑터에 윈도우 ICS(인터넷 연결 공유) 기본 게이트웨이 IP인 `192.168.137.1`과 서브넷 마스크(`255.255.255.0`)가 정확히 바인딩되어 있는지 검증.
3. **클라이언트 기기 IP 할당 (DHCP) 확인:**
   - [ ] 핫스팟에 연결하는 스마트폰 등 클라이언트 기기가 `192.168.137.x` 대역의 IP를 DHCP로 정상 할당받는지, ARP 테이블 조회 및 WinRT `ClientCount`를 통해 IP 충돌이나 무한 'IP 주소 가져오는 중' 현상 없이 통신 가능한지 검증.

---

## 9. 핫스팟 클라이언트 격리 방화벽 제어 규격 (Hotspot Client Isolation & Firewall Rules)
핫스팟 구동 시 연결된 사용자(고객 기기) 상호 간의 무단 통신 및 매장 호스트 PC의 내부 공유 자원 접근을 차단하기 위해 **[체크 ➔ 설정 ➔ 검증]** 3단계 PASS/FAIL 시나리오를 강제 적용한다.

### Step 1. 체크 (Check) 단계: 사전 상태 확인
방화벽 규칙을 새로 만들거나 수정하기 전에, 현재 환경이 올바른지 검사:
- **[Check 1] 관리자 권한 확인:**
  - 스크립트/애플리케이션 실행 주체가 관리자 권한인지 확인 (`ctypes.windll.shell32.IsUserAnAdmin`).
  - **판정:** 관리자 아님 ➔ **[FAIL]** (중단 및 관리자 권한 요구) / 관리자 맞음 ➔ **[PASS]**
- **[Check 2] 핫스팟 어댑터 및 IP 대역 확인:**
  - 현재 핫스팟이 켜져 있으며, 대상 서브넷(`192.168.137.0/24`) 및 게이트웨이(`192.168.137.1`)가 활성화되어 있는지 확인.
  - **판정:** 미작동 ➔ **[FAIL]** (핫스팟 먼저 켜도록 안내) / 정상 ➔ **[PASS]**
- **[Check 3] 기존 방화벽 규칙 중복 여부 확인:**
  - 이미 동일한 이름의 규칙(`Hotspot-Web-Allow`, `Hotspot-SMB-Block`)이 존재하는지 확인.
  - **판정:** 존재함 ➔ 기존 규칙 삭제(갱신 준비) / 없음 ➔ **[PASS]**

### Step 2. 설정 (Configure) 단계: 방화벽 규칙 적용
체크 단계를 모두 통과(PASS)하면 실제 윈도우 고급 방화벽(NetFirewall) 규칙 적용:
- **[Config 1] 웹 서비스 포트 허용 규칙 추가 (`Hotspot-Web-Allow`):**
  - 핫스팟 대역(`192.168.137.0/24`)에서 호스트 PC의 파일 전송/승인 웹 포트(예: 5000 또는 8080)로 들어오는 인바운드 TCP 트래픽을 허용(Allow).
  - **수행 결과:** 성공 ➔ **[PASS]** / 실패(명령어 오류 등) ➔ **[FAIL]**
- **[Config 2] 내부 파일 공유(SMB) 차단 규칙 적용 (`Hotspot-SMB-Block` & `FPS-SMB-In-TCP`):**
  - 핫스팟 대역에서 호스트 PC의 파일 공유 기능(SMB, TCP 445/139) 접근을 차단(Block).
  - **수행 결과:** 성공 ➔ **[PASS]** / 실패 ➔ **[FAIL]**

### Step 3. 검증 (Verify) 단계: 결과 확인 및 테스트
설정 직후 시스템 쿼리를 통해 방화벽 규칙이 의도대로 정확히 등록·활성화되었는지 검증:
- **[Verify 1] 허용 규칙 등록 여부 검증:**
  - 파워셸/CIM 쿼리를 통해 `Hotspot-Web-Allow` 규칙이 실제로 활성화(`Enabled=True`) 및 `Action=Allow` 상태로 존재하는지 조회.
  - **판정:** 규칙 없음 또는 비활성 ➔ **[FAIL]** / 정상 등록됨 ➔ **[PASS]**
- **[Verify 2] 차단 규칙 적용 여부 검증:**
  - `FPS-SMB-In-TCP` 및 `Hotspot-SMB-Block` 규칙의 `RemoteAddress`에 핫스팟 대역(`192.168.137.0/24`)이 정확히 지정되어 있고 `Action`이 `Block`인지 확인.
  - **판정:** 설정값 불일치 ➔ **[FAIL]** / 정상 적용됨 ➔ **[PASS]**

---

## 10. 공통 비동기 로깅 시스템 및 로그 디렉토리 규격 (Common Queued Logging Architecture)
시스템의 모든 기능은 비동기 큐(`queue.Queue` 및 백그라운드 워커 스레드) 기반의 공통 로깅 엔진(`Common.logger_service`)을 사용하며 디스크 I/O 병목 및 UI 스레드 블로킹을 방지한다.

### 10.1. 디렉토리 및 파일명 명명 규칙
- **로그 기본 경로:** `data/log/<큰기능_디렉토리>/`
- **로그 파일명 형식:** `<YYYYMMDD>_<LOG_TAG>.LOG` (예: `20261021_WIFI.LOG`, `20261021_SECURITY.LOG`, `20261021_PRINT.LOG`)
- **로그 라인 형식:** `YYYY-MM-DD HH:MM:SS,mmm [LEVEL] [LOG_TAG] 로그 메시지` (UTF-8 with BOM 인코딩)

### 10.2. 주요 기능별 디렉토리 및 태그 분류

| 큰 기능 디렉토리 (`feature`) | 로그 태그 (`tag`) | 대상 로그 파일 | 설명 |
| :--- | :--- | :--- | :--- |
| `hotspot` | `WIFI` | `YYYYMMDD_WIFI.LOG` | 모바일 핫스팟 구동, SSID/비밀번호 변경, 연결 진단 로그 |
| `firewall` | `SECURITY` | `YYYYMMDD_SECURITY.LOG` | 핫스팟 클라이언트 격리 방화벽 체크/설정/검증 이력 |
| `printer` | `PRINT` | `YYYYMMDD_PRINT.LOG` | Windows 스풀러 및 WMI 인쇄 이벤트 로깅 |
| `printer` | `DETECT` | `YYYYMMDD_DETECT.LOG` | 인쇄 검출, 주문 트리 매칭, 트레이 추가 이력 |
| `linkbox` | `TRANSFER` | `YYYYMMDD_TRANSFER.LOG` | 고객 파일 업로드 수신 및 전송 완료 이력 |
| `linkshare` | `USAGE` | `YYYYMMDD_USAGE.LOG` | Wi-Fi 이용권 요청, 관리자 승인, 이용 만료 세션 이력 |
| `order` | `APPROVAL` / `ROLLBACK` | `YYYYMMDD_APPROVAL.LOG` 등 | 작업자 주문 상태 전이, 승인 및 롤백 제어 이력 |

---

## 11. 통합 Hotspot 설정 탭 및 검증·충돌 방지 규격 (Unified Hotspot Settings & Validation)
핫스팟 설정의 직관성과 연결 안정성을 위해 기존의 분리된 Hotspot 탭과 Network 탭을 단일 **Hotspot** 탭으로 통합하고, NIC 식별·사전 IP Ping 충돌 검사·사후 유효성 검증 및 실패 항목 시각화(Red Highlight)를 적용한다.

### 11.1. 설정 UI 통합 및 콤팩트 구성
- **탭 통합:** `IntegratedSettingsDialog` 내의 Hotspot 및 Network 탭을 하나의 **Hotspot** 탭으로 일원화.
- **UI 레이아웃 최적화:** 여백 및 위젯 간격을 최소화(Spacing 4px, Margins 8px)하여 스크롤 없이 주요 네트워크 및 핫스팟 파라미터를 한 화면에서 즉시 조작 가능하도록 콤팩트하게 구성.
- **UI 항목 배치 순서 (상단부터):**
  1. `Internet NIC (internet line)`: 외부 인터넷 인입선 어댑터 선택
  2. `Hotspot NIC (recommended wireless adapter)`: Wi-Fi 송출용 무선 어댑터 선택
  3. `Hotspot gateway IP`: 핫스팟 게이트웨이 고정 IP (기본값: `192.168.137.1`)
  4. `Hotspot IPv4 range (CIDR)`: 핫스팟 클라이언트 IP 서브넷 대역 (기본값: `192.168.137.0/24`)
- **NIC별 물리 MAC 주소 표시:** 인터넷 인입용 NIC 및 핫스팟 송출용 NIC 콤보박스에 어댑터 명칭, IPv4 주소와 함께 하드웨어 물리 주소를 `[MAC: XX:XX:XX:XX:XX:XX]` 형식으로 자동 표기하여 동일 칩셋/어댑터 간 오인 방지.

### 11.2. 핫스팟 시작 전 APIPA(`169.254.x.x`) 표기 방지 및 게이트웨이 IP 사전 바인딩 규격
- 윈도우 모바일 핫스팟이 아직 활성화되지 않은 대기 상태에서는 물리/가상 무선 랜카드가 임시 링크-로컬 주소(`169.254.x.x`)를 가지는 현상이 발생함.
- 사용자가 핫스팟 NIC를 선택하거나 UI에 표시할 때, `169.254.x.x` 임시 주소 대신 설정된 Hotspot gateway IP(`192.168.137.1`)로 바인딩하여 표시하고 검증(PASS)하도록 처리.
- 게이트웨이 IP를 변경하는 경우 핫스팟 NIC 콤보박스의 바인딩 IP 표기도 실시간 연동되어 갱신됨.

### 11.3. IP 할당 전 Ping 충돌 검사 및 분기 처리
- **사전 충돌 검사:** 사용자가 입력한 게이트웨이 IP(예: `192.168.137.1`)를 시스템에 반영하기 전, 로컬 호스트에 바인딩되어 있지 않은 외부 IP일 경우 ICMP Ping(`ping -n 1 -w 600`)을 사전 전송.
- **분기 처리:**
  - **Ping 응답 수신 시 (충돌 위험):** 네트워크 상에 동일 IP를 사용하는 기기가 이미 활성화되어 있음을 감지하고, 경고 팝업(`QMessageBox.warning`)을 띄워 사용자에게 충돌 위험을 고지하고 계속 진행 여부를 확인.
  - **Ping 미응답 시 (정상):** 충돌 없음으로 판단하여 검증 통과 및 안전하게 설정 적용 단계로 진행.

### 11.4. 설정 항목별 사후 검증 및 결과 영속화 (Config Storage)
- **검증 대상 항목:**
  - `hotspot_gateway`: 유효한 IPv4 형식, CIDR 서브넷 범위 포함 여부, Ping 충돌 여부.
  - `hotspot_network`: 유효한 CIDR 표기법(`192.168.137.0/24`) 및 IPv4 네트워크 규격.
  - `hotspot_nic`: 어댑터 선택 여부 및 정상 연결 상태(APIPA `169.254.x.x` 제외).
  - `internet_nic`: 인터넷 인입선 연결 여부 및 정상 IPv4 할당 상태.
- **검증 결과 저장:** 각 항목별 PASS / FAIL 상태를 `wifi_approval_settings.ini`의 `[Settings]` 섹션 내 `hotspot_validation_results` (JSON 형식)에 개별 저장.

```ini
[Settings]
hotspot_validation_results = {"hotspot_gateway": "PASS", "hotspot_network": "PASS", "hotspot_nic": "PASS", "internet_nic": "PASS"}
```

### 11.5. 설정 화면 로딩 시 실패 항목 시각적 강조 (Red Highlighting)
- 설정 화면(`IntegratedSettingsDialog`)을 로딩할 때, `hotspot_validation_results`를 조회하여 검증 상태가 FAIL로 저장된 항목의 입력 필드 또는 콤보박스 테두리와 배경색을 **빨간색**(`border: 1px solid #d32f2f; background-color: #ffebee;`)으로 표시하고 상세 원인을 툴팁으로 제공.

---

## 12. 물리 어댑터 기반 인터넷 NIC 및 핫스팟 NIC 자동 결정 규칙 (Physical NIC Decision Rules)
가상 터널 어댑터(Tailscale, Cloudflare WARP 등) 및 내부 가상 Wi-Fi 다이렉트 어댑터의 오선택을 방지하고 물리적 하드웨어 장치만을 기준으로 인터넷 인입선과 핫스팟 송출 어댑터를 정확히 분리하기 위한 6대 결정 규칙:

### 12.1. 6대 결정 조건 (Decision Conditions)
1. **인터넷 우선 매핑:** 물리 장치 중 인터넷 통신이 확인된(Default Gateway 보유 및 외부 연결 성공) 어댑터는 우선적으로 인터넷 NIC(`internet_nic`)로 지정.
2. **복수 인터넷 연결 시 유선(Ethernet) 우선:** 두 개 이상의 물리 장치가 모두 인터넷이 되는 경우, 안정적인 대역폭 보장을 위해 유선 랜카드를 인터넷 NIC로 우선 배정.
3. **단일 인터넷 연결 시 역할 분리:** 두 개의 물리 어댑터 중 하나만 인터넷이 가능하고 다른 하나는 인터넷이 안 되는 경우, 인터넷이 되는 어댑터를 인터넷 NIC, 인터넷이 안 되는 어댑터를 핫스팟 송출 NIC(`hotspot_nic`)로 자동 배정.
4. **인터넷 전면 불가 시 FAIL 처리:** 모든 물리 어댑터에서 인터넷 통신이 불가한 경우, 인터넷 NIC는 미선택(FAIL) 상태로 처리하여 무효한 가상 IP 연결을 차단.
5. **물리 하드웨어 장치 한정 (Physical Only):** Windows NCF 특성 플래그(`NCF_PHYSICAL=0x4`, `NCF_VIRTUAL=0x1` 제외)를 검사하여 실제 메인보드 및 USB 슬롯에 장착된 물리적 네트워크 카드만을 판별 대상으로 한정 (Tailscale, WARP, 가상 WAN 미니포트 등 배제).
6. **복수 NIC 환경 순위:** 물리 NIC가 여러 개일 경우 인터넷 어댑터는 **유선 ➔ 무선 ➔ 링크 속도(Link Speed) 빠른 순**으로 최종 결정.

---

## 13. 프로그램 시작 최적화: 사전 체크(Check-First) 기본 정책 및 MAC 주소 영속화

### 13.1. 사전 체크(Check-First) 기본 정책
- **배경 및 목적:** 프로그램 시작 시 장비 제어 명령(WinRT 테더링 API, PowerShell 방화벽 규칙 적용, 네트워크 라우트 재탐색 등)을 무조건 호출하면 윈도우 OS 시스템 블로킹으로 인해 앱 구동 시간이 수 초 이상 지연됨.
- **기본 원칙:**
  1. **설정 필요 시 선행 체크:** 장치나 소프트웨어 구성 변경이 필요할 때 먼저 현재 상태가 기 설정값과 일치하는지 신속하게 사전 체크 수행.
  2. **체크 성공 시 중복 설정 생략:**
     - **네트워크 어댑터 매칭:** 기존 설정(`print_shop_config.ini` / `wifi_approval_settings.ini`)에 저장된 어댑터가 현재 UP 상태이며 유효한 IP/MAC을 유지하고 있으면 하드웨어 재스캔 및 ICMP 핑 테스트를 건너뛰고 즉시 바인딩.
     - **핫스팟 자격증명(SSID/비밀번호):** 시스템에 활성화된 핫스팟의 SSID 및 비밀번호가 앱 설정과 일치하면 WinRT 자격증명 변경 루틴을 호출하지 않음.
     - **핫스팟 활성화 상태:** 핫스팟이 이미 동작 중(`OperationalState == 1` 또는 게이트웨이 `192.168.137.1` 활성)인 경우 불필요한 Hotspot ON 재시작을 수행하지 않고 기존 상태 유지.
     - **클라이언트 격리 방화벽:** 시스템 방화벽에 `Hotspot-Web-Allow` 및 `Hotspot-SMB-Block` 규칙이 이미 올바르게 적용되어 있다면 PowerShell 기반의 삭제/재생성 과정을 생략(`skip_if_already_valid=True`).

### 13.2. NIC MAC 주소 영속화 (Config Storage)
- **설정 파일 반영 규격:** `[Network]` 섹션에 `internet_mac`과 `hotspot_mac` 필드를 추가하여 영구 저장.

```ini
[Network]
internet_nic = Wi-Fi (192.168.1.5) [MAC: 30:03:C8:7C:8C:97]
internet_ip = 192.168.1.5
internet_mac = 30:03:C8:7C:8C:97
hotspot_nic = Local Area Connection* 13 (192.168.137.1) [MAC: A0:47:D7:21:A4:9D]
hotspot_ip = 192.168.137.1
hotspot_mac = A0:47:D7:21:A4:9D
hotspot_network = 192.168.137.0/24
hotspot_gateway = 192.168.137.1
```

- **가상 어댑터(Wi-Fi Direct) 매핑:** Windows 모바일 핫스팟 구동 시 실제 IP `192.168.137.1`을 점유하는 `Local Area Connection* 13` 등의 가상 Wi-Fi Direct 어댑터 MAC 주소를 정확하게 추출 및 보존하여 재시작 시 오선택 방지.