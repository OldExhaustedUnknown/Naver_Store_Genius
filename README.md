# Naver Store Genius

네이버 스마트스토어 **지정 시간 자동 구매** 프로그램

선착순/한정판 상품을 정확한 시간에 자동으로 구매합니다.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| **예약 구매** | 날짜/시/분/초 단위로 구매 시간 예약 |
| **NTP 동기화** | 5개 NTP 서버 fallback, ms 단위 정밀 타이밍 |
| **자동 로그인** | 세션 만료 시 자동 재로그인 (2FA 지원) |
| **보안 자격증명** | Windows Credential Manager 암호화 저장 |
| **이중 구매 방지** | 동일 세션 중복 주문 차단 |
| **옵션/수량** | 상품 옵션 3개 + 수량 자동 설정 |
| **모던 GUI** | CustomTkinter 다크 테마, 실시간 카운트다운 |
| **EXE 빌드** | PyInstaller 원클릭 빌드 + 바탕화면 바로가기 |

---

## 스크린샷

```
┌─ SmartStore Auto Buyer ─────────────── [대기 중] ┐
│              02:34:15.827                         │
│  ████████████░░░░░░░░░░░░░░░░░░                  │
│                                                   │
│  네이버 로그인 (Windows 자격증명 저장소)            │
│  네이버 ID  [____________]                        │
│  비밀번호   [****]                                │
│  [자격증명 저장] [자격증명 삭제]                    │
│                                                   │
│  상품 URL   [https://smartstore.naver.com/...]     │
│  구매 일시  [2026-03-25] [11]:[00]:[00]           │
│  수량       [1]                                   │
│                                                   │
│  옵션1 [2]  옵션2 [__]  옵션3 [__]                │
│                                                   │
│  [✔] NTP 시간 동기화   사전이동: [30]초            │
│                                                   │
│  [예약 시작]   [중지]   [설정 저장]                │
│                                                   │
│  [13:25:01] NTP 동기화 완료 (-65.7ms)             │
│  [13:25:03] Chrome 연결 성공                      │
│  [13:25:04] 네이버 로그인 상태 확인됨              │
└───────────────────────────────────────────────────┘
```

---

## 설치 및 실행

### 방법 1: Python 직접 실행

```bash
# 의존성 설치
pip install -r requirements.txt

# 실행
python app.py
```

### 방법 2: EXE 빌드

```bash
# build.bat 실행 (빌드 + 바탕화면 바로가기 생성)
build.bat
```

또는 수동:

```bash
pip install -r requirements.txt pyinstaller
pyinstaller build.spec --noconfirm --clean
python create_shortcut.py
```

`dist/SmartStoreAutoBuyer.exe` 생성됨 (약 42MB, 단일 파일)

---

## 사용법

### 1. 네이버 로그인 설정

1. 프로그램 실행
2. 네이버 ID / 비밀번호 입력
3. **[자격증명 저장]** 클릭 → Windows Credential Manager에 암호화 저장
4. 비밀번호는 화면에서 즉시 삭제됨

> 2단계 인증 사용 시: 자동 로그인 시도 후 브라우저에서 직접 인증 (60초 대기)

### 2. 구매 예약

1. **상품 URL** 입력 (스마트스토어 상품 페이지)
2. **구매 일시** 설정 (YYYY-MM-DD HH MM SS)
3. **수량** 입력 (1~99)
4. **옵션** 입력 (필요시, 몇 번째 옵션인지 숫자 입력)
5. **[예약 시작]** 클릭

### 3. 자동 구매 프로세스

```
NTP 동기화 → Chrome 연결 → 로그인 확인
→ 예약시간 30초 전 페이지 이동 → 카운트다운
→ 정각에 새로고침 → 옵션/수량 설정 → 구매 클릭 → 결제
```

---

## 아키텍처

```
app.py              ← GUI (CustomTkinter)
├── scheduler.py    ← 예약 스케줄러 (별도 스레드)
│   ├── ntp_sync.py ← NTP 동기화 + 3단계 정밀 대기
│   └── browser.py  ← Chrome 자동화 + 자동 로그인
├── config.json     ← 설정 (비밀번호 미포함)
└── app_icon.ico    ← 앱 아이콘
```

### 핵심 설계

- **Chrome Debugger 포트 (9222)**: 기존 Chrome 세션 재활용, 봇 탐지 우회
- **NTP 3단계 대기**: >2초: sleep(0.5) → 0.1~2초: sleep(0.01) → <0.1초: busy-wait
- **Windows Credential Manager**: OS 수준 암호화, config.json에 비밀번호 없음
- **이중 구매 방지**: `_purchase_completed` 플래그로 동일 세션 중복 주문 차단

---

## 기술 스택

| 구성 | 기술 |
|------|------|
| GUI | CustomTkinter 5.2+ |
| 브라우저 자동화 | Selenium 4.15+ |
| 시간 동기화 | ntplib (NTP) |
| 자격증명 보안 | keyring (Windows Credential Manager) |
| 아이콘 생성 | Pillow |
| 빌드 | PyInstaller 6.x |

---

## 파일 구조

```
├── app.py                 # GUI 메인 애플리케이션
├── browser.py             # Chrome 자동화 + 자동 로그인
├── scheduler.py           # 예약 스케줄러
├── ntp_sync.py            # NTP 시간 동기화
├── create_icon.py         # 앱 아이콘 생성
├── create_shortcut.py     # 바탕화면 바로가기 생성
├── build.spec             # PyInstaller 빌드 설정
├── build.bat              # 원클릭 빌드 스크립트
├── config.json            # 설정 파일
├── requirements.txt       # Python 의존성
├── app_icon.ico           # 앱 아이콘
└── app_icon.png           # 아이콘 미리보기
```

---

## 주의사항

- 이 프로그램은 **교육/학습 목적**으로 제작되었습니다
- 웹사이트 이용약관을 확인하고 사용하세요
- 과도한 사용은 계정 제한을 받을 수 있습니다
- 실제 결제가 이루어지므로 설정을 신중히 확인하세요

---

## 라이선스

MIT License
