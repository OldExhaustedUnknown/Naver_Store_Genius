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
    os.environ.get("LOCALAPPDATA", r"C:\Users\Public"), "chrometemp_autobuyer"
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
        self._purchase_lock = threading.Lock()  # M1 수정: 스레드 안전
        self._purchase_completed = False
        self._chrome_process: Optional[subprocess.Popen] = None  # M4 수정: 프로세스 추적
        self._debugger_port: int = 0

    def _find_chrome(self) -> str:
        for path in CHROME_PATHS:
            if os.path.isfile(path):
                return path
        raise FileNotFoundError("Chrome 실행 파일을 찾을 수 없습니다.")

    def launch_chrome(self, profile_path: str = "") -> None:
        """디버거 포트가 열린 Chrome 인스턴스 실행 (C1 수정: list-based Popen)"""
        chrome_path = self._find_chrome()
        user_data = profile_path or CHROME_TEMP_DIR
        self._debugger_port = _find_free_port()

        # C1 수정: shell=True → list 기반, 인젝션 불가
        cmd = [
            chrome_path,
            f"--remote-debugging-port={self._debugger_port}",
            f"--user-data-dir={user_data}",
        ]
        self._chrome_process = subprocess.Popen(cmd)
        self.log(f"Chrome 실행 (port={self._debugger_port})")

        # 연결 대기: 고정 sleep 대신 retry
        for _ in range(10):
            time.sleep(0.5)
            try:
                with socket.create_connection(("127.0.0.1", self._debugger_port), timeout=1):
                    break
            except (ConnectionRefusedError, OSError):
                continue

    def connect(self) -> webdriver.Chrome:
        """실행 중인 Chrome에 연결"""
        options = webdriver.ChromeOptions()
        options.add_experimental_option(
            "debuggerAddress", f"127.0.0.1:{self._debugger_port}"
        )
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])

        self.driver = webdriver.Chrome(options=options)
        self.driver.implicitly_wait(5)
        self.log("Chrome 연결 성공")
        return self.driver

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
