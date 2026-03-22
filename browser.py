# -*- coding: utf-8 -*-
"""브라우저 자동화 모듈 — Chrome debugger 포트 + 자동 로그인
감사 수정: C1(shell injection), C3(고정포트), M1(race), M4(프로세스 누수), M5(URL 검증)
"""

import socket
import subprocess
import threading
import time
import os
from typing import Optional
from urllib.parse import urlparse

import keyring
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    ElementClickInterceptedException,
    WebDriverException,
)

KEYRING_SERVICE = "smartstore_autobuyer"

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]

CHROME_TEMP_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", r"C:\Users\Public"), "NaverStoreGenius_chrome"
)


# ── 자격증명 관리 (Windows Credential Manager) ──

def save_credentials(naver_id: str, naver_pw: str) -> None:
    keyring.set_password(KEYRING_SERVICE, "naver_id", naver_id)
    keyring.set_password(KEYRING_SERVICE, "naver_pw", naver_pw)


def load_credentials() -> tuple[Optional[str], Optional[str]]:
    nid = keyring.get_password(KEYRING_SERVICE, "naver_id")
    npw = keyring.get_password(KEYRING_SERVICE, "naver_pw")
    return nid, npw


def delete_credentials() -> None:
    try:
        keyring.delete_password(KEYRING_SERVICE, "naver_id")
        keyring.delete_password(KEYRING_SERVICE, "naver_pw")
    except keyring.errors.PasswordDeleteError:
        pass


def save_api_key(api_key: str) -> None:
    keyring.set_password(KEYRING_SERVICE, "anthropic_api_key", api_key)


def load_api_key() -> Optional[str]:
    # 1. 환경변수 우선
    env_key = os.environ.get("ANTHROPIC_API_KEY")
    if env_key:
        return env_key
    # 2. keyring fallback
    return keyring.get_password(KEYRING_SERVICE, "anthropic_api_key")


def delete_api_key() -> None:
    try:
        keyring.delete_password(KEYRING_SERVICE, "anthropic_api_key")
    except keyring.errors.PasswordDeleteError:
        pass


def _find_free_port() -> int:
    """사용 가능한 랜덤 포트 반환 (C3 수정: 고정 포트 제거)"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def validate_smartstore_url(url: str) -> bool:
    """네이버 스마트스토어 URL 검증 (M5 수정)"""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        return hostname.endswith(".naver.com") and parsed.scheme in ("http", "https")
    except Exception:
        return False


class BrowserManager:
    """Chrome debugger 포트를 통한 브라우저 제어 + 자동 로그인"""

    def __init__(self, log_callback=None):
        self.driver: Optional[webdriver.Chrome] = None
        self.log = log_callback or print
        self._purchase_lock = threading.Lock()
        self._purchase_completed = False
        self._chrome_process: Optional[subprocess.Popen] = None
        self._debugger_port: int = 0
        self._chromedriver_path: str = ""  # 생성 시 1회 resolve

    def _find_chrome(self) -> str:
        for path in CHROME_PATHS:
            if os.path.isfile(path):
                return path
        raise FileNotFoundError("Chrome 실행 파일을 찾을 수 없습니다.")

    def launch_chrome(self, profile_path: str = "") -> None:
        """전용 프로필로 독립된 Chrome 인스턴스 실행.

        일반 Chrome과 완전히 공존 — user-data-dir이 다르면 별개 프로세스.
        같은 전용 프로필의 이전 인스턴스가 있으면 lock 파일만 정리.
        """
        chrome_path = self._find_chrome()
        user_data = profile_path or CHROME_TEMP_DIR
        self._debugger_port = _find_free_port()

        # 이전 세션의 lock 파일 정리 (비정상 종료 대응)
        for name in ["lockfile", "SingletonLock", "SingletonSocket", "SingletonCookie"]:
            lf = os.path.join(user_data, name)
            if os.path.exists(lf):
                try:
                    os.remove(lf)
                except OSError:
                    pass

        cmd = [
            chrome_path,
            f"--remote-debugging-port={self._debugger_port}",
            f"--user-data-dir={user_data}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        self._chrome_process = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        self.log(f"Chrome 실행 (port={self._debugger_port})")

        # Chrome이 즉시 종료되면 이전 전용 인스턴스가 이미 실행 중
        time.sleep(1.5)
        if self._chrome_process.poll() is not None:
            # 이전 전용 Chrome의 debugger 포트를 찾아서 재사용하는 건 어렵기 때문에
            # 사용자에게 안내
            self.log("이전에 열린 전용 Chrome 창을 닫고 다시 시도해주세요.")
            raise RuntimeError(
                "전용 Chrome이 이미 실행 중입니다. "
                "이전에 열린 'Naver Store Genius' Chrome 창을 닫고 다시 시도하세요."
            )

        # 포트 대기 (최대 10초)
        for i in range(20):
            time.sleep(0.5)
            try:
                with socket.create_connection(("127.0.0.1", self._debugger_port), timeout=1):
                    self.log("Chrome 준비 완료")
                    return
            except (ConnectionRefusedError, OSError):
                continue

        self.log("경고: Chrome 포트 대기 타임아웃 — 연결을 시도합니다")

    def _resolve_chromedriver(self) -> str:
        """chromedriver 경로 확보 — 앱 번들 > 캐시 > Selenium Manager 순"""
        import glob
        import sys

        # 1. 앱과 같은 디렉토리에 번들된 chromedriver
        app_dir = os.path.dirname(os.path.abspath(__file__))
        # PyInstaller EXE인 경우 _MEIPASS 경로도 체크
        if hasattr(sys, "_MEIPASS"):
            bundled = os.path.join(sys._MEIPASS, "chromedriver.exe")
            if os.path.exists(bundled):
                return bundled
        bundled = os.path.join(app_dir, "chromedriver.exe")
        if os.path.exists(bundled):
            return bundled

        # 2. Selenium 캐시
        cache_dir = os.path.join(os.path.expanduser("~"), ".cache", "selenium", "chromedriver")
        candidates = glob.glob(os.path.join(cache_dir, "**", "chromedriver.exe"), recursive=True)
        if candidates:
            candidates.sort(reverse=True)
            return candidates[0]

        # 3. Selenium Manager로 다운로드 (최초 1회)
        self.log("chromedriver 다운로드 중 (최초 1회)...")
        for p in sys.path:
            se = os.path.join(p, "selenium", "webdriver", "common", "windows", "selenium-manager.exe")
            if os.path.exists(se):
                result = subprocess.run(
                    [se, "--browser", "chrome", "--output", "json"],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode == 0:
                    import json as _json
                    data = _json.loads(result.stdout)
                    driver_path = data.get("result", {}).get("driver_path", "")
                    if driver_path and os.path.exists(driver_path):
                        return driver_path
                break

        return ""

    def connect(self) -> webdriver.Chrome:
        """실행 중인 Chrome에 연결"""
        from selenium.webdriver.chrome.service import Service

        options = webdriver.ChromeOptions()
        options.add_experimental_option(
            "debuggerAddress", f"127.0.0.1:{self._debugger_port}"
        )

        # chromedriver 경로: 최초 1회만 resolve, 이후 캐싱
        if not self._chromedriver_path:
            self._chromedriver_path = self._resolve_chromedriver()
            if self._chromedriver_path:
                self.log(f"chromedriver: {os.path.basename(self._chromedriver_path)}")
        chromedriver_path = self._chromedriver_path

        last_error = None
        for attempt in range(1, 4):
            try:
                self.log(f"Chrome 연결 시도 {attempt}/3...")
                if chromedriver_path:
                    svc = Service(chromedriver_path)
                    self.driver = webdriver.Chrome(service=svc, options=options)
                else:
                    self.driver = webdriver.Chrome(options=options)
                self.driver.implicitly_wait(5)
                self.log("Chrome 연결 성공")
                return self.driver
            except Exception as e:
                last_error = e
                self.log(f"연결 실패 {attempt}/3: {type(e).__name__}: {str(e)[:80]}")
                time.sleep(2)

        raise ConnectionError(f"Chrome 연결 실패 (3회): {last_error}")

    # ── 로그인 ──

    def is_logged_in(self) -> bool:
        """네이버 로그인 상태 확인"""
        try:
            self.driver.get("https://nid.naver.com/user2/help/myInfo")
            time.sleep(1.5)
            current_url = self.driver.current_url
            if "nidlogin.login" in current_url or "login" in current_url.split("?")[0]:
                return False
            return True
        except WebDriverException:
            return False

    def login(self, naver_id: str = "", naver_pw: str = "") -> bool:
        """네이버 자동 로그인 — ID/PW 입력 + 캡챠 자동 풀이(Claude API)

        플로우:
        1. 로그인 페이지 이동
        2. ID/PW 클립보드 붙여넣기
        3. 로그인 버튼 클릭
        4. 캡챠 감지 시 → 스크린샷 → Claude API → 답 입력 → 재시도
        5. 로그인 완료 감지
        """
        if not naver_id or not naver_pw:
            naver_id, naver_pw = load_credentials()
        if not naver_id or not naver_pw:
            self.log("로그인 자격증명이 없습니다.")
            return False

        try:
            self.driver.get(
                "https://nid.naver.com/nidlogin.login?mode=form&url=https%3A%2F%2Fwww.naver.com"
            )
            time.sleep(1.5)

            # ID/PW 입력 (클립보드 붙여넣기)
            self._input_credentials(naver_id, naver_pw)

            # 로그인 버튼 클릭
            login_btn = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, ".btn_login, #log\\.login, button[type='submit']")
                )
            )
            login_btn.click()
            time.sleep(2)

            # 로그인 결과 확인 (최대 3회 캡챠 시도)
            for attempt in range(3):
                current_url = self.driver.current_url
                if "nidlogin" not in current_url and "login" not in current_url.split("?")[0]:
                    self.log("네이버 로그인 성공!")
                    return True

                # 캡챠 감지
                if self._detect_captcha():
                    self.log(f"캡챠 감지 — AI로 풀이 시도 ({attempt + 1}/3)...")
                    if self._solve_captcha():
                        # 캡챠 풀이 후 로그인 버튼 재클릭
                        time.sleep(1)
                        try:
                            btn = self.driver.find_element(
                                By.CSS_SELECTOR, ".btn_login, #log\\.login, button[type='submit']"
                            )
                            btn.click()
                        except NoSuchElementException:
                            pass
                        time.sleep(2)
                        continue
                    else:
                        self.log("캡챠 풀이 실패")
                else:
                    # 캡챠 없이 로그인 실패 — 추가 인증 또는 수동 대기
                    self.log("브라우저에서 직접 로그인을 완료해주세요 (120초 대기)")
                    for _ in range(120):
                        time.sleep(1)
                        try:
                            url = self.driver.current_url
                            if "nidlogin" not in url and "login" not in url.split("?")[0]:
                                self.log("로그인 완료 감지!")
                                return True
                        except WebDriverException:
                            pass
                    break

            # 최종 확인
            current_url = self.driver.current_url
            if "nidlogin" not in current_url and "login" not in current_url.split("?")[0]:
                self.log("로그인 성공!")
                return True

            self.log("로그인 실패 — ID/PW를 확인하세요.")
            return False

        except Exception as e:
            self.log(f"로그인 오류: {e}")
            return False

    def _input_credentials(self, naver_id: str, naver_pw: str) -> None:
        """ID/PW를 클립보드 붙여넣기로 입력"""
        import pyperclip
        from selenium.webdriver.common.keys import Keys

        id_el = WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input#id, input[name='id']"))
        )
        id_el.click()
        time.sleep(0.2)
        pyperclip.copy(naver_id)
        id_el.send_keys(Keys.CONTROL, "a")
        id_el.send_keys(Keys.CONTROL, "v")
        time.sleep(0.3)

        pw_el = self.driver.find_element(By.CSS_SELECTOR, "input#pw, input[name='pw']")
        pw_el.click()
        time.sleep(0.2)
        pyperclip.copy(naver_pw)
        pw_el.send_keys(Keys.CONTROL, "a")
        pw_el.send_keys(Keys.CONTROL, "v")
        time.sleep(0.3)

        pyperclip.copy("")  # 클립보드 정리

    def _detect_captcha(self) -> bool:
        """캡챠 존재 여부 감지"""
        try:
            page = self.driver.page_source
            captcha_keywords = ["자동입력 방지", "captcha", "ncaptcha", "정답을 입력"]
            return any(kw in page for kw in captcha_keywords)
        except Exception:
            return False

    def _solve_captcha(self) -> bool:
        """로그인 캡챠 풀이 — _solve_page_captcha와 동일 로직 사용"""
        return self._solve_page_captcha()

    def _capture_captcha_image(self) -> Optional[bytes]:
        """캡챠 이미지 영역을 스크린샷으로 캡처"""
        try:
            # 캡챠 이미지 요소 찾기
            captcha_selectors = [
                "img#captchaimg",
                "img[id*='captcha']",
                "img[src*='captcha']",
                "div.captcha_wrap img",
                "div[class*='captcha'] img",
                "#captcha img",
            ]
            for selector in captcha_selectors:
                try:
                    elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    return elem.screenshot_as_png
                except NoSuchElementException:
                    continue

            # 캡챠 영역 전체 스크린샷 (이미지를 못 찾으면)
            captcha_area_selectors = [
                "div.captcha_wrap",
                "div[class*='captcha']",
                "#captcha",
            ]
            for selector in captcha_area_selectors:
                try:
                    elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    return elem.screenshot_as_png
                except NoSuchElementException:
                    continue

            # 최후의 수단: 전체 페이지 스크린샷
            self.log("캡챠 요소 미발견 — 전체 페이지 캡처")
            return self.driver.get_screenshot_as_png()

        except Exception as e:
            self.log(f"캡챠 캡처 오류: {e}")
            return None

    def ensure_logged_in(self) -> bool:
        """로그인 상태 확인 후 필요시 자동 로그인"""
        if self.is_logged_in():
            self.log("네이버 로그인 상태 확인됨")
            return True
        self.log("로그인 세션 만료 — 자동 로그인 시도...")
        return self.login()

    def minimize_window(self) -> None:
        """Chrome 창 최소화"""
        try:
            self.driver.minimize_window()
            self.log("Chrome 창 최소화")
        except Exception:
            pass

    def restore_window(self) -> None:
        """Chrome 창 복원"""
        try:
            self.driver.set_window_position(0, 0)
            self.driver.maximize_window()
        except Exception:
            pass

    # ── 페이지 조작 ──

    def navigate(self, url: str) -> None:
        self.driver.get(url)
        self.log(f"페이지 이동: {url[:60]}...")
        time.sleep(1)
        # 페이지 접근 시 캡챠 감지 → 자동 풀이
        if self._detect_captcha():
            self.log("페이지 접근 캡챠 감지 — AI 풀이 시도...")
            for attempt in range(3):
                if self._solve_page_captcha():
                    time.sleep(2)
                    if not self._detect_captcha():
                        self.log("캡챠 통과!")
                        break
                    self.log(f"캡챠 재시도 {attempt + 2}/3...")
                else:
                    break

    def _solve_page_captcha(self) -> bool:
        """페이지 접근 캡챠 풀이 — 질문 텍스트 + 이미지를 Claude에 전송"""
        api_key = load_api_key()
        if not api_key:
            self.log("Claude API 키가 없어 캡챠를 풀 수 없습니다.")
            return False

        try:
            import base64
            import re
            import anthropic

            # 1. 질문 텍스트 추출
            question_text = self._extract_captcha_question()
            self.log(f"캡챠 질문: {question_text}")

            # 2. 캡챠 이미지 캡처
            captcha_img = self._capture_captcha_image()
            if not captcha_img:
                return False

            # 3. Claude API 호출 — 질문 텍스트 + 이미지
            client = anthropic.Anthropic(api_key=api_key)
            img_b64 = base64.b64encode(captcha_img).decode("utf-8")

            prompt = (
                f"네이버 보안 캡챠입니다.\n\n"
                f"질문: {question_text}\n\n"
                f"위 이미지(영수증 등)를 분석하여 질문에 대한 정답만 답해주세요.\n"
                f"규칙:\n"
                f"- [?] 또는 빈 칸에 들어갈 값만 출력\n"
                f"- 숫자만 필요하면 숫자만 (하이픈, 쉼표 등 기호 절대 포함하지 마세요)\n"
                f"- 텍스트가 필요하면 텍스트만\n"
                f"- 다른 설명, 문장, 부연 없이 정답만 한 줄로 출력\n"
                f"- 예시: 질문이 '새재길 [?]'이면 도로명 뒤 번지수만 출력 (예: 243)"
            )

            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=50,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": img_b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }],
            )

            answer = message.content[0].text.strip()
            # 후처리: 숫자만 필요한 경우 숫자 외 문자 제거
            if question_text and ("[?]" in question_text or "빈 칸" in question_text):
                clean = re.sub(r"[^\d]", "", answer)
                if clean:
                    answer = clean
            self.log(f"캡챠 답: {answer}")

            # 4. 답 입력
            input_selectors = [
                "input[placeholder*='정답']",
                "input[placeholder*='입력']",
                "input#captcha",
                "input[name='captcha']",
            ]
            for selector in input_selectors:
                try:
                    inp = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if inp.is_displayed():
                        inp.clear()
                        inp.send_keys(answer)
                        time.sleep(0.3)
                        break
                except NoSuchElementException:
                    continue
            else:
                # 마지막 fallback: 보이는 text input
                try:
                    inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='text']")
                    for inp in inputs:
                        if inp.is_displayed() and inp.get_attribute("type") != "hidden":
                            inp.clear()
                            inp.send_keys(answer)
                            break
                except Exception:
                    pass

            # 5. 확인 버튼 클릭
            for cs in ["//button[contains(text(),'확인')]", "button[type='submit']", "button[class*='btn_confirm']"]:
                try:
                    if cs.startswith("//"):
                        btn = self.driver.find_element(By.XPATH, cs)
                    else:
                        btn = self.driver.find_element(By.CSS_SELECTOR, cs)
                    btn.click()
                    self.log("캡챠 답 제출")
                    return True
                except NoSuchElementException:
                    continue

            return False
        except Exception as e:
            self.log(f"캡챠 풀이 오류: {e}")
            return False

    def _extract_captcha_question(self) -> str:
        """캡챠 페이지에서 질문 텍스트 추출"""
        try:
            page = self.driver.page_source
            # 빨간/초록 강조 텍스트에 질문이 있음
            question_selectors = [
                "span[class*='highlight']",
                "p[class*='question']",
                "strong[class*='question']",
                "div[class*='captcha'] p",
                "div[class*='captcha'] span",
            ]
            for selector in question_selectors:
                try:
                    elems = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for elem in elems:
                        text = elem.text.strip()
                        if text and ("?" in text or "[?]" in text or "빈 칸" in text):
                            return text
                except Exception:
                    continue

            # 전체 페이지에서 질문 패턴 추출
            import re
            patterns = [
                r"(영수증[^.]*\?[^.]*\.)",
                r"(가게[^.]*\?[^.]*\.)",
                r"([^.]*\[?\?\][^.]*\.)",
                r"([^.]*빈 칸[^.]*\.)",
                r"(구매한[^.]*\?)",
                r"(총[^.]*종류[^.]*\?)",
            ]
            for pat in patterns:
                match = re.search(pat, page)
                if match:
                    return match.group(1).strip()

            # 마지막 수단: 보이는 텍스트 중 질문 같은 것
            try:
                body_text = self.driver.find_element(By.TAG_NAME, "body").text
                for line in body_text.split("\n"):
                    line = line.strip()
                    if "?" in line or "[?]" in line or "빈 칸" in line:
                        return line
            except Exception:
                pass

            return "(질문을 찾을 수 없음)"
        except Exception:
            return "(질문 추출 실패)"

    def extract_product_options(self) -> list[dict]:
        """현재 페이지에서 상품 옵션 목록을 추출.

        Returns: [{"name": "소금간 선택", "values": ["순한맛", "보통맛", ...]}]
        """
        results = []
        try:
            time.sleep(1)

            # 드롭다운 그룹 찾기 — 여러 셀렉터 시도
            group_selectors = [
                "div[class*='option_area'] > div",
                "div[class*='_optionArea'] > div",
                "div[class*='select_box']",
                "div[class*='_selectOption']",
                "div[class*='option_group']",
            ]

            groups = []
            for sel in group_selectors:
                groups = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if groups:
                    break

            if not groups:
                # 단일 드롭다운 페이지
                groups = self.driver.find_elements(
                    By.CSS_SELECTOR,
                    "div[class*='select'] > button, div[class*='select'] > a[role='button']"
                )

            for idx, group in enumerate(groups):
                option_info = {"name": f"옵션 {idx + 1}", "values": []}
                try:
                    # 드롭다운 제목 추출
                    title_el = group.find_element(By.CSS_SELECTOR, "label, span, button")
                    title = title_el.text.strip()
                    if title:
                        option_info["name"] = title

                    # 드롭다운 클릭하여 옵션 목록 열기
                    clickable = group.find_elements(By.CSS_SELECTOR, "button, a[role='button'], a")
                    if clickable:
                        clickable[0].click()
                        time.sleep(0.5)

                        # 옵션 항목 추출
                        items = self.driver.find_elements(
                            By.CSS_SELECTOR,
                            "li[class*='option'], ul[role='listbox'] li, ul[class*='opt'] li, div[class*='option_list'] li"
                        )
                        for item in items:
                            text = item.text.strip()
                            if text and text != option_info["name"]:
                                option_info["values"].append(text)

                        # 드롭다운 닫기 (Escape)
                        from selenium.webdriver.common.keys import Keys
                        try:
                            self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                        except Exception:
                            pass
                        time.sleep(0.3)

                except Exception:
                    pass

                if option_info["values"]:
                    results.append(option_info)

            if results:
                self.log(f"옵션 {len(results)}개 그룹 추출 완료")
            else:
                self.log("추출 가능한 옵션이 없습니다 (옵션 없는 상품이거나 품절)")

        except Exception as e:
            self.log(f"옵션 추출 오류: {e}")

        return results

    def wait_and_click(self, by: str, value: str, timeout: int = 10) -> bool:
        try:
            elem = WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable((by, value))
            )
            elem.click()
            return True
        except (TimeoutException, ElementClickInterceptedException) as e:
            self.log(f"클릭 실패 [{value[:30]}]: {e}")
            return False

    def is_product_available(self) -> bool:
        """상품 구매 가능 여부 확인 (품절/미오픈 체크)"""
        try:
            page_source = self.driver.page_source
            # 품절 키워드 체크
            soldout_keywords = ["품절", "SOLD OUT", "sold out", "매진", "구매불가"]
            for kw in soldout_keywords:
                if kw in page_source:
                    return False

            # 구매 버튼 존재 여부
            buy_selectors = [
                (By.CSS_SELECTOR, "a[class*='_buyButton'], button[class*='_buyButton']"),
                (By.XPATH, "//a[contains(text(),'구매하기')]"),
                (By.XPATH, "//button[contains(text(),'구매하기')]"),
                (By.XPATH, "//a[contains(text(),'바로구매')]"),
            ]
            for by, selector in buy_selectors:
                try:
                    elem = self.driver.find_element(by, selector)
                    if elem.is_displayed() and elem.is_enabled():
                        return True
                except NoSuchElementException:
                    continue

            return False
        except Exception:
            return False

    def select_option_by_text(self, option_text: str, option_group: int = 1) -> bool:
        """상품 옵션을 텍스트로 선택.

        option_text: 선택할 옵션 텍스트 (예: "순한맛", "L", "블랙")
                     숫자만 입력하면 N번째 옵션 선택 (하위 호환)
        option_group: 몇 번째 드롭다운인지 (1부터)
        """
        # 숫자만 입력된 경우 → N번째 옵션 선택
        is_index = option_text.isdigit()

        # 드롭다운 찾기 — 여러 셀렉터 시도
        dropdown_selectors = [
            "div[class*='_selectOption'] > div, div[class*='select_box']",
            "a[role='button'][class*='select']",
            "div[class*='_optionSelect']",
            "div[class*='option'] > button, div[class*='option'] > a",
            # 스크린샷에서 본 "소금간 선택" 같은 드롭다운
            "div[class*='select'] button, div[class*='select'] a",
        ]

        dropdown = None
        for selector in dropdown_selectors:
            try:
                elems = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if len(elems) >= option_group:
                    dropdown = elems[option_group - 1]
                    break
            except Exception:
                continue

        if not dropdown:
            # XPath로 재시도 — 텍스트로 드롭다운 찾기
            try:
                dropdowns = self.driver.find_elements(
                    By.XPATH,
                    "//div[contains(@class,'select')]//button | //div[contains(@class,'select')]//a[@role='button']"
                )
                if len(dropdowns) >= option_group:
                    dropdown = dropdowns[option_group - 1]
            except Exception:
                pass

        if not dropdown:
            self.log(f"옵션 드롭다운 {option_group}번째를 찾을 수 없습니다.")
            return False

        # 드롭다운 클릭하여 옵션 목록 열기
        try:
            dropdown.click()
            time.sleep(0.5)
        except Exception as e:
            self.log(f"드롭다운 클릭 실패: {e}")
            return False

        # 옵션 항목 찾기
        item_selectors = [
            "li[class*='option']",
            "ul[class*='option'] li",
            "div[class*='option_list'] li",
            "ul[role='listbox'] li",
            "div[class*='select'] ul li",
        ]

        items = []
        for selector in item_selectors:
            try:
                items = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if items:
                    break
            except Exception:
                continue

        if not items:
            # XPath 재시도
            try:
                items = self.driver.find_elements(
                    By.XPATH, "//ul[contains(@class,'opt')]//li | //ul[@role='listbox']//li"
                )
            except Exception:
                pass

        if not items:
            self.log("옵션 항목을 찾을 수 없습니다.")
            return False

        # 옵션 선택
        if is_index:
            idx = int(option_text)
            if 1 <= idx <= len(items):
                try:
                    items[idx - 1].click()
                    self.log(f"옵션 {option_group}번 드롭다운에서 {idx}번째 항목 선택")
                    return True
                except Exception as e:
                    self.log(f"옵션 클릭 실패: {e}")
                    return False
            else:
                self.log(f"옵션 인덱스 {idx}가 범위 밖 (총 {len(items)}개)")
                return False
        else:
            # 텍스트 매칭
            for item in items:
                try:
                    item_text = item.text.strip()
                    if option_text in item_text or item_text in option_text:
                        item.click()
                        self.log(f"옵션 선택: '{item_text}'")
                        return True
                except Exception:
                    continue

            # 부분 매칭 재시도
            for item in items:
                try:
                    item_text = item.text.strip().lower()
                    if option_text.lower() in item_text:
                        item.click()
                        self.log(f"옵션 선택 (부분매칭): '{item.text.strip()}'")
                        return True
                except Exception:
                    continue

            available = [it.text.strip() for it in items[:10] if it.text.strip()]
            self.log(f"'{option_text}' 옵션을 찾을 수 없음. 가능한 옵션: {available}")
            return False

    def set_quantity(self, quantity: int) -> bool:
        """수량 설정"""
        if quantity <= 1:
            return True
        try:
            qty_selectors = [
                (By.CSS_SELECTOR, "input[class*='quantity'], input[class*='count']"),
                (By.CSS_SELECTOR, "input[type='number']"),
                (By.XPATH, "//input[contains(@title,'수량')]"),
            ]
            for by, selector in qty_selectors:
                try:
                    elem = self.driver.find_element(by, selector)
                    elem.clear()
                    elem.send_keys(str(quantity))
                    self.log(f"수량 {quantity}개 설정")
                    return True
                except NoSuchElementException:
                    continue

            # +버튼 방식
            plus_selectors = [
                (By.CSS_SELECTOR, "button[class*='plus'], a[class*='plus']"),
                (By.XPATH, "//button[contains(@class,'up') or contains(@class,'plus')]"),
            ]
            for by, selector in plus_selectors:
                try:
                    btn = self.driver.find_element(by, selector)
                    for _ in range(quantity - 1):
                        btn.click()
                        time.sleep(0.05)
                    self.log(f"수량 {quantity}개 설정 (+버튼)")
                    return True
                except NoSuchElementException:
                    continue

            self.log("수량 필드 미발견 — 기본 수량(1)")
            return False
        except Exception as e:
            self.log(f"수량 설정 오류: {e}")
            return False

    def click_buy_button(self) -> bool:
        """구매하기 버튼 클릭"""
        with self._purchase_lock:
            if self._purchase_completed:
                self.log("이중 구매 방지: 이미 구매 완료")
                return False

            buy_selectors = [
                (By.CSS_SELECTOR, "a[class*='_buyButton'], button[class*='_buyButton']"),
                (By.CSS_SELECTOR, "a[class*='buy'], button[class*='buy']"),
                (By.XPATH, "//a[contains(text(),'구매하기')]"),
                (By.XPATH, "//button[contains(text(),'구매하기')]"),
                (By.XPATH, "//a[contains(text(),'바로구매')]"),
                (By.XPATH, "//*[@id='content']//fieldset//div[9]/div[1]/div/a"),
            ]
            for by, selector in buy_selectors:
                try:
                    elem = self.driver.find_element(by, selector)
                    elem.click()
                    self._purchase_completed = True  # 즉시 플래그
                    self.log("구매 버튼 클릭!")
                    return True
                except NoSuchElementException:
                    continue

        self.log("구매 버튼을 찾을 수 없습니다.")
        return False

    def process_payment(self) -> bool:
        """결제 페이지 처리 (구매 버튼 이후 단계)"""
        try:
            self.wait_and_click(
                By.XPATH,
                "//*[contains(@class, 'chargePoint') or contains(@id, 'chargePoint')]//li[4]//span",
                timeout=5,
            )
            time.sleep(0.3)

            self.wait_and_click(
                By.XPATH,
                "//*[contains(text(), '나중에 결제') or contains(text(), '무통장')]//ancestor::span | //*[contains(text(), '나중에 결제')]",
                timeout=5,
            )
            time.sleep(0.3)

            order_selectors = [
                (By.XPATH, "//*[@id='orderForm']//button[contains(text(),'결제')]"),
                (By.XPATH, "//button[contains(text(),'결제하기')]"),
                (By.CSS_SELECTOR, "button[class*='confirm'], button[class*='order']"),
            ]
            for by, selector in order_selectors:
                try:
                    elem = self.driver.find_element(by, selector)
                    elem.click()
                    with self._purchase_lock:
                        self._purchase_completed = True
                    self.log("주문 요청 전송 완료!")
                    return True
                except NoSuchElementException:
                    continue

            self.log("결제 버튼 미발견 — 수동 결제 필요")
            return False

        except Exception as e:
            self.log(f"결제 처리 오류: {e}")
            return False

    def reset_purchase_flag(self):
        with self._purchase_lock:
            self._purchase_completed = False

    def quit(self) -> None:
        """브라우저 + Chrome 프로세스 정리 (M3/M4 수정)"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
        if self._chrome_process:
            try:
                self._chrome_process.terminate()
                self._chrome_process.wait(timeout=5)
            except Exception:
                pass
            self._chrome_process = None
