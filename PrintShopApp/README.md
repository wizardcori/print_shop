# PrintShopApp 프로젝트 요약

PrintShopApp은 매장 PC를 로컬 서버로 사용해 고객의 파일 전송과 Wi-Fi 이용권 승인을 한 화면에서 관리하는 Windows용 Python 데스크톱 애플리케이션입니다.

## 핵심 기능

- **LinkBox**: 고객이 QR 코드로 접속해 여러 파일을 업로드하고, 관리자가 위치별 수신 파일과 전송 로그를 관리합니다.
- **LinkShare**: 고객의 인터넷 이용 시간 요청을 받고, 관리자가 승인·거절하며 세션 상태와 요금 로그를 관리합니다.
- **통합 관리자**: `main_app.py`가 두 기능을 하나의 PySide6 화면에 배치합니다.
- **네트워크 자동 선택**: 사용 가능한 IPv4 인터페이스를 찾고 인터넷 연결 여부와 Wi-Fi 여부를 기준으로 우선순위를 정합니다.
- **NIC 자동 검색 및 분리**: 인터넷 연결이 확인된 NIC와 핫스팟에 적합한 무선 NIC를 각각 추천하고, `Rescan NIC`로 다시 검색할 수 있습니다.
- **핫스팟 설정**: 핫스팟 SSID, 핫스팟용 무선 NIC, 표시 이미지를 설정 화면에서 선택할 수 있습니다.
- **설정 메뉴**: 모든 환경 설정은 메인 화면 상단의 `Settings > Open Settings` 메뉴에서 변경합니다.
- **핫스팟 진단·제어**: 핫스팟 탭에서 IP 대역과 게이트웨이를 확인하고, 진단 결과를 보며 `Hotspot ON`, `Hotspot OFF`, `Run diagnosis`를 사용할 수 있습니다.
- **최대 연결 수**: 설정 메뉴에서 최대 연결 수를 지정할 수 있으며 기본값은 `250`입니다. 상태는 `현재 연결 수 / 최대 연결 수`로 표시되고, 한도에 도달하면 새 요청을 거부합니다.
- **QR 코드 제공**: 선택한 네트워크 주소와 매장 위치를 포함한 접속 URL을 QR 코드로 표시합니다.
- **보안**: LinkBox 단독 서버는 HTTPS를 사용하고, LinkShare 이용권 로그는 Fernet 키로 보호합니다.

## 기술 구성

| 영역 | 구성 |
| --- | --- |
| 데스크톱 UI | Python 3.11, PySide6 |
| 웹 서버 | Flask(통합/LinkShare), `http.server` + TLS(LinkBox) |
| QR 코드 | `qrcode`, Pillow |
| 암호화 | `cryptography.fernet.Fernet` |
| 네트워크 상태 | `psutil`, Python socket, Windows WinRT tethering API |
| 배포 | PyInstaller onedir |

## 실행 방법

`PrintShopApp` 폴더에서 다음 순서로 실행합니다.

```bat
setup.bat
run.bat
```

`setup.bat`은 Python 3.11을 확인하고 `.venv`를 생성한 뒤 필요한 패키지와 LinkBox용 자체 서명 인증서를 준비합니다. 배포본은 다음 명령으로 생성합니다.

```bat
dist.bat
```

## 주요 경로

- [main_app.py](./main_app.py): 통합 애플리케이션 진입점 및 Flask 라우트
- [ui_layout.py](./ui_layout.py): 통합 UI 레이아웃
- [LinkBox/src](./LinkBox/src): 통합 PrintShop 앱에서 사용하는 파일 수신·프린터 모니터 기능
- [LinkShare/src](./LinkShare/src): 통합 PrintShop 앱의 Wi-Fi 승인·세션·요금 기능
- [doc/Directory Structure.txt](./doc/Directory%20Structure.txt): 프로젝트 구조와 실행 중 생성되는 파일

## 설정 저장

통합 앱의 설정은 [wifi_approval_settings.ini](./wifi_approval_settings.ini)에 저장·복원됩니다.

- `[Network]`: 인터넷 NIC와 핫스팟 NIC의 이름·IP, 핫스팟 IPv4 CIDR 대역과 게이트웨이
- `[Settings]`: 핫스팟 SSID, 핫스팟 이미지, 이용권 로그 폴더, 최대 연결 수
- `[Storage]`: 업로드 폴더, 구역 목록, 저장 탭 목록
- `[Security]`: LinkShare Fernet 암호화 키

설정 파일에 저장된 NIC가 더 이상 존재하지 않으면 다음 실행 시 현재 검색 결과에서 인터넷 연결 NIC와 무선 NIC를 다시 자동 선택합니다.

핫스팟 기본 대역은 Windows 모바일 핫스팟의 일반적인 `192.168.137.0/24`, 게이트웨이는 `192.168.137.1`입니다. 진단 및 핫스팟 활성화 루틴은 다음 6대 체크포인트를 준수하여 검증합니다:

1. **인터넷 인입용 체크포인트 (인터넷 소스 어댑터)**
   - [ ] **연결 상태 확인 (Media State)**: 인입 어댑터의 미디어 연결 여부 및 유효한 IPv4 할당 상태
   - [ ] **게이트웨이 및 인터넷 통신 확인**: 상위 공유기 게이트웨이 및 외부 인터넷(1.1.1.1, 8.8.8.8) 통신 가능 여부
   - [ ] **윈도우 모바일 핫스팟 공유 소스 매칭**: Windows ICS '다음에서 인터넷 연결 공유' 어댑터 일치 여부
2. **핫스팟용 체크포인트 (와이파이 송출 어댑터)**
   - [ ] **핫스팟 어댑터 활성화 여부**: Wi-Fi Direct 가상 어댑터(Local Area Connection*)의 UP 상태
   - [ ] **고정 IP(192.168.137.1) 할당 여부**: ICS 게이트웨이 IP 및 255.255.255.0 서브넷 마스크 바인딩 상태
   - [ ] **클라이언트 기기 IP 할당 (DHCP) 확인**: 192.168.137.x 대역 내 기기 연결 및 ARP/WinRT 클라이언트 확인

진단 루틴은 위 항목을 기반으로 `ON`, `PARTIAL`, `READY`, `OFF` 상태와 세부 체크포인트 결과를 표시합니다.

### 핫스팟 클라이언트 격리 방화벽 제어 (Check ➔ Configure ➔ Verify)
핫스팟 구동 시 연결된 사용자 기기간 불필요한 통신 및 호스트 PC 파일 공유(SMB) 접근을 차단하기 위해 3단계 방화벽 제어 로직을 적용합니다:
- **Step 1 (Check)**: 관리자 권한 확인, 핫스팟 서브넷(192.168.137.0/24) 상태 확인, 기존 `Hotspot-Web-Allow` 중복 여부 확인
- **Step 2 (Configure)**: 웹 서비스 포트(5000/8080) 인바운드 허용(`Hotspot-Web-Allow`), 내부 파일 공유(SMB, 445/139) 차단(`FPS-SMB-In-TCP`, `Hotspot-SMB-Block`)
- **Step 3 (Verify)**: 시스템 방화벽 쿼리를 통한 허용 규칙 활성화 상태 및 차단 규칙 `RemoteAddress`/`Action=Block` 적용 여부 검증

### 기능별 공통 비동기 로깅 규격 (Common Queued Logger)
- **로그 디렉토리 분리**: `data/log/<큰기능_디렉토리>/` (`hotspot`, `firewall`, `printer`, `linkbox`, `linkshare`, `order` 등)
- **로그 파일명 형식**: `<YYYYMMDD>_<TAG>.LOG` (예: `20261021_WIFI.LOG`, `20261021_SECURITY.LOG`, `20261021_PRINT.LOG`)
- **로그 큐 기반 비동기 처리**: `Common.logger_service`의 백그라운드 큐 워커를 통해 대량 로깅 시에도 I/O 블로킹 방지

### 설정 시 기본 정책: 사전 체크(Check-First) 및 중복 작업 생략
- **목적**: 앱 기동 속도 개선 및 불필요한 OS 리소스 호출 차단 (핫스팟 점검, 방화벽 설정, 네트워크 NIC 판별 등).
- **동작 원칙**:
  1. **사전 체크 (Check-first)**: 장치나 설정이 필요할 때 먼저 현재 상태가 요구사항을 만족하고 있는지 검사합니다.
  2. **중복 생략 (Bypass redundant calls)**:
     - 저장된 NIC 정보가 유효하고 현재 장치와 일치하면 무거운 하드웨어 재탐색 및 ping 라우트 검사를 건너뜁니다.
     - 핫스팟 SSID 및 암호가 이미 시스템과 일치하면 WinRT 자격증명 업데이트를 생략합니다.
     - 핫스팟이 이미 켜져 있고 192.168.137.1 게이트웨이가 정상이면 중복 ON 명령을 호출하지 않습니다.
     - 클라이언트 격리 방화벽 규칙(Hotspot-Web-Allow, Hotspot-SMB-Block)이 이미 올바르게 등록되어 있으면 PowerShell 규칙 재생성 호출을 건너뜁니다.

### 통합 Hotspot 탭 및 네트워크 어댑터 관리 규격
- **탭 통합**: 기존 Settings의 Hotspot 탭과 Network 탭을 하나의 콤팩트한 Hotspot 탭으로 통합.
- **MAC 주소 영속화**: [Network] 섹션에 internet_mac 및 hotspot_mac 필드를 저장하여 어댑터 식별 안정성 확보.
- **IP 변경 사전 핑 검증**: 게이트웨이/IP 수동 할당 전 네트워크에 ICMP 핑을 전송하여 충돌 여부 사전 확인 및 사용자 확인 팝업 제공.
- **설정 사후 검증 및 실패 항목 시각화**: 저장 시 각 항목별 유효성을 검증하여 [Settings] 섹션의 hotspot_validation_results JSON으로 저장하며, 다이얼로그 로딩 시 실패 항목은 빨간색으로 표시.
- **가상 Wi-Fi Direct 어댑터 인식**: Windows 모바일 핫스팟 구동 시 생성되는 가상 어댑터(Local Area Connection* 13 등)에 192.168.137.1이 할당된 경우, 핫스팟 활성 어댑터로 정확히 매핑하여 UI 및 설정에 실시간 반영.

### 물리 어댑터 기반 인터넷 NIC 및 핫스팟 NIC 결정 규칙
- **물리 장치 한정 (`NCF_PHYSICAL`)**: VPN/터널 가상 어댑터(Tailscale, WARP 등) 및 가상 미니포트를 제외하고 실제 물리 랜카드만 후보군으로 식별.
- **6대 결정 규칙 준수**:
  1. 인터넷이 되는 NIC는 `인터넷 NIC(internet_nic)`로 우선 배정.
  2. 둘 다 인터넷이 되는 경우 유선 랜카드(Ethernet)를 우선 배정.
  3. 두 개 중 하나만 인터넷이 되는 경우, 되는 쪽을 `인터넷 NIC`, 안 되는 쪽을 `핫스팟 NIC(hotspot_nic)`로 분리 배정.
  4. 둘 다 인터넷이 안 되면 `인터넷 NIC`는 FAIL(미선택) 처리.
  5. 물리적인 하드웨어 장치만 판단 대상으로 한정.
  6. NIC가 여러 개일 경우 인터넷은 **유선 $\rightarrow$ 무선 $\rightarrow$ 링크 속도가 빠른 순**으로 결정.





Windows Mobile Hotspot의 실제 SSID는 WinRT에서 먼저 읽고, 프로그램 시작 시 항상 프로그램 지정값 `hb_wifi`로 변경합니다. 핫스팟이 켜져 있고 `192.168.137.1` 게이트웨이가 감지되면 QR 접속 URL도 인터넷 NIC 주소가 아닌 핫스팟 게이트웨이 주소를 사용합니다.

`Hotspot ON`과 `Hotspot OFF`는 Windows WinRT `NetworkOperatorTetheringManager`를 우선 사용합니다. WinRT 구성 요소가 없거나 장치가 지원하지 않으면 `netsh`를 시도하고, 실패 시 Windows 모바일 핫스팟 설정 화면을 엽니다. 최초 설치 또는 환경 재설정 시 `setup.bat`을 다시 실행해 WinRT 네트워크 패키지를 설치해야 합니다.

## 현재 상태 및 주의 사항

- 통합 Flask 앱은 `LinkShare/templates/portal.html`과 `LinkBox/templates/file_share.html`을 참조합니다.
- `cert.pem`, `key.pem`, `wifi_approval_settings.ini`에는 운영 환경의 인증서·암호화 키·설정이 포함될 수 있으므로 외부 공유와 버전 관리 시 주의해야 합니다.
- 테스트 자동화와 패키지 고정 파일(`requirements.txt`)은 아직 제공되지 않습니다.
## Windows 모바일 핫스팟 실제 장치 제한

프로그램은 Windows WinRT `NetworkOperatorTetheringManager`의 `ClientCount`와
`MaxClientCount`를 진단 화면에 표시합니다. 현재 장치에서 Windows가 실제로 표시하는
값은 `1 of 8`처럼 표시되며, 앱의 `[Settings] max_connections` 값(기본값 250)과는
별개의 제한입니다.

`MaxClientCount`는 지원되는 WinRT API에서 읽기 전용입니다. 따라서 프로그램의 설정 메뉴에서
250으로 바꾸어도 Windows 모바일 핫스팟의 실제 `of 8` 값이 바뀌지는 않으며, 앱 서버가 새
요청을 거부하는 애플리케이션 한도만 변경됩니다. Windows 실제 제한을 변경하려면 Windows
버전·무선 어댑터·모바일 브로드밴드 프로비저닝 정책을 확인해야 하며, 비공식 레지스트리 변경은
관리자 권한, 핫스팟 중지 및 재부팅이 필요할 수 있으므로 자동 적용하지 않습니다.
설정 메뉴의 `Apply Windows limit (registry)` 버튼은 이 비공식 방법을 사용자가 직접
실행할 때만 레지스트리에 `WifiMaxPeers` 값을 기록합니다. 값의 허용 범위는 1~128이며,
관리자 권한이 없으면 변경하지 않고 안내 메시지를 표시합니다. 적용 후에는 모바일 핫스팟을
껐다 켜야 하며, Windows가 이전 값을 계속 표시하면 재부팅해야 합니다.

- **Hotspot 탭 UI 컨트롤 순서 및 게이트웨이 IP 동기화**:
  - Internet NIC $\rightarrow$ Hotspot NIC $\rightarrow$ Hotspot gateway IP $\rightarrow$ Hotspot IPv4 range (CIDR) 순서로 배치.
  - 핫스팟 구동 전 무선 랜카드의 임시 링크-로컬 APIPA(169.254.x.x) 노출을 방지하고, 지정된 Hotspot gateway IP(192.168.137.1)로 사전 바인딩하여 표시 및 검증 통과 처리.