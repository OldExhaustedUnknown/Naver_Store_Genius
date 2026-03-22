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
        """chromedriver 경로를 미리 확보 (Selenium Manager 지연 방지)"""
        import glob

        # 1. 캐시에서 직접 찾기
        cache_dir = os.path.join(os.path.expanduser("~"), ".cache", "selenium", "chromedriver")
        candidates = glob.glob(os.path.join(cache_dir, "**", "chromedriver.exe"), recursive=True)
        if candidates:
            # 가장 최신 버전 사용
            candidates.sort(reverse=True)
            return candidates[0]

        # 2. Selenium Manager 실행하여 다운로드
        self.log("chromedriver 다운로드 중 (최초 1회)...")
        import subprocess as _sp
        import sys
        for p in sys.path:
            se = os.path.join(p, "selenium", "webdriver", "common", "windows", "selenium-manager.exe")
            if os.path.exists(se):
                result = _sp.run(
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

        return ""  # fallback: Selenium이 자동 관리

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
        """네이버 로그인 수행"""
        if not naver_id or not naver_pw:
            naver_id, naver_pw = load_credentials()
        if not naver_id or not naver_pw:
            self.log("로그인 자격증명이 없습니다. GUI에서 설정해주세요.")
            return False

        try:
            self.driver.get(
                "https://nid.naver.com/nidlogin.login?mode=form&url=https%3A%2F%2Fwww.naver.com"
            )
            time.sleep(1)

            # JavaScript로 ID/PW 입력
            script = """
            (function() {
                var id_el = document.querySelector('#id');
                var pw_el = document.querySelector('#pw');
                if (id_el) {
                    id_el.focus();
                    id_el.value = arguments[0];
                    id_el.dispatchEvent(new Event('input', {bubbles: true}));
                }
                if (pw_el) {
                    pw_el.focus();
                    pw_el.value = arguments[1];
                    pw_el.dispatchEvent(new Event('input', {bubbles: true}));
                }
            })();
            """
            self.driver.execute_script(script, naver_id, naver_pw)
            time.sleep(0.5)

            login_btn = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".btn_login, #log\\.login"))
            )
            login_btn.click()
            time.sleep(2)

            current_url = self.driver.current_url
            if "nidlogin" not in current_url:
                self.log("네이버 로그인 성공")
                return True

            self.log("로그인 추가 인증 필요 — 브라우저에서 직접 완료해주세요 (60초 대기)")
            for _ in range(60):
                time.sleep(1)
                if "nidlogin" not in self.driver.current_url:
                    self.log("수동 인증 완료, 로그인 성공")
                    return True
            self.log("로그인 타임아웃 (60초)")
            return False

        except Exception as e:
            self.log(f"로그인 실패: {e}")
            return False

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

    def select_option(self, option_index: int, option_group: int) -> bool:
        """상품 옵션 선택"""
        # 레거시 XPath
        try:
            self.driver.find_element(
                By.XPATH,
                f"//*[@id='content']//fieldset//div[5]/div[{option_group}]/a"
            ).click()
            time.sleep(0.3)
            self.driver.find_element(
                By.XPATH,
                f"//*[@id='content']//fieldset//div[5]/div[{option_group}]/ul/li[{option_index}]"
            ).click()
            self.log(f"옵션 {option_group}-{option_index} 선택")
            return True
        except NoSuchElementException:
            pass

        # CSS (최신)
        try:
            dropdowns = self.driver.find_elements(
                By.CSS_SELECTOR,
                "a[role='button'][class*='select'], div[class*='_optionSelect']"
            )
            if len(dropdowns) >= option_group:
                dropdowns[option_group - 1].click()
                time.sleep(0.3)
                options = self.driver.find_elements(By.CSS_SELECTOR, "li[class*='option']")
                if len(options) >= option_index:
                    options[option_index - 1].click()
                    self.log(f"옵션 {option_group}-{option_index} 선택 (CSS)")
                    return True
        except Exception as e:
            self.log(f"옵션 선택 실패: {e}")
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
        """구매하기 버튼 클릭 (M1 수정: 스레드 안전)"""
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
                self.log("구매 버튼 클릭!")
                return True
            except NoSuchElementException:
                continue

        self.log("구매 버튼을 찾을 수 없습니다.")
        return False

    def process_payment(self) -> bool:
        """결제 페이지 처리"""
        with self._purchase_lock:
            if self._purchase_completed:
                self.log("이중 구매 방지: 이미 결제 완료")
                return False

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
