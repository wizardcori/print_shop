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
- [LinkBox/linkbox_app.py](./LinkBox/linkbox_app.py): 파일 수신 기능
- [LinkShare/linkshare_app.py](./LinkShare/linkshare_app.py): 이용권 승인 및 로그 기능
- [doc/Directory Structure.txt](./doc/Directory%20Structure.txt): 프로젝트 구조와 실행 중 생성되는 파일

## 설정 저장

통합 앱의 설정은 [wifi_approval_settings.ini](./wifi_approval_settings.ini)에 저장·복원됩니다.

- `[Network]`: 인터넷 NIC와 핫스팟 NIC의 이름·IP, 핫스팟 IPv4 CIDR 대역과 게이트웨이
- `[Settings]`: 핫스팟 SSID, 핫스팟 이미지, 이용권 로그 폴더, 최대 연결 수
- `[Storage]`: 업로드 폴더, 구역 목록, 저장 탭 목록
- `[Security]`: LinkShare Fernet 암호화 키

설정 파일에 저장된 NIC가 더 이상 존재하지 않으면 다음 실행 시 현재 검색 결과에서 인터넷 연결 NIC와 무선 NIC를 다시 자동 선택합니다.

핫스팟 기본 대역은 Windows 모바일 핫스팟의 일반적인 `192.168.137.0/24`, 게이트웨이는 `192.168.137.1`입니다. 진단 루틴은 선택된 무선 어댑터의 연결 상태와 실제 IPv4 주소를 확인해 `ON`, `PARTIAL`, `READY`, `OFF` 상태로 표시합니다.

Windows Mobile Hotspot의 실제 SSID는 WinRT에서 먼저 읽고, 프로그램 시작 시 항상 프로그램 지정값 `hb_wifi`로 변경합니다. 핫스팟이 켜져 있고 `192.168.137.1` 게이트웨이가 감지되면 QR 접속 URL도 인터넷 NIC 주소가 아닌 핫스팟 게이트웨이 주소를 사용합니다.

`Hotspot ON`과 `Hotspot OFF`는 Windows WinRT `NetworkOperatorTetheringManager`를 우선 사용합니다. WinRT 구성 요소가 없거나 장치가 지원하지 않으면 `netsh`를 시도하고, 실패 시 Windows 모바일 핫스팟 설정 화면을 엽니다. 최초 설치 또는 환경 재설정 시 `setup.bat`을 다시 실행해 WinRT 네트워크 패키지를 설치해야 합니다.

## 현재 상태 및 주의 사항

- 통합 Flask 앱은 `LinkShare/templates/portal.html`과 `LinkShare/templates/file_share.html`을 참조하지만, 현재 저장소에는 해당 템플릿이 없습니다. 따라서 `/scan`과 `/file_share` 화면을 실제로 사용하려면 두 템플릿을 추가해야 합니다.
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
