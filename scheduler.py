# -*- coding: utf-8 -*-
"""스케줄러 모듈 — 예약 시간 + 재시도 로직 (무인 운영)
감사 수정: M2(threading.Event), M3(리소스 정리)
"""

import random
import threading
import time as _time
from datetime import datetime, timedelta
from typing import Callable, Optional

from ntp_sync import NTPSync
from browser import BrowserManager


# 재시도 프리셋
RETRY_PRESETS = {
    "fast":   {"interval": 0.5, "max_retries": 120, "label": "빠름 (0.5초 x 120회 = 1분)"},
    "normal": {"interval": 1.0, "max_retries": 60,  "label": "보통 (1초 x 60회 = 1분)"},
    "safe":   {"interval": 2.0, "max_retries": 30,  "label": "안전 (2초 x 30회 = 1분)"},
}

MAX_RETRY_HARDCAP = 300  # 절대 최대 재시도


class PurchaseScheduler:
    """예약 시간 기반 자동 구매 스케줄러 — 재시도 + 무인 운영"""

    def __init__(self, log_callback: Callable = print):
        self.log = log_callback
        self.ntp = NTPSync()
        self.browser = BrowserManager(log_callback=log_callback)
        self._stop_event = threading.Event()  # M2 수정
        self._thread: Optional[threading.Thread] = None
        self.on_countdown: Optional[Callable] = None
        self.on_complete: Optional[Callable] = None
        self.on_retry_update: Optional[Callable] = None  # (current, max, status)

        # 재시도 설정
        self.retry_enabled = True
        self.retry_interval = 1.0
        self.retry_max = 60
        self.retry_jitter = 0.1  # ±초 랜덤 지터

    def configure(
        self,
        product_url: str,
        purchase_time: datetime,
        options: dict,
        quantity: int = 1,
        use_ntp: bool = True,
        ntp_server: str = "time.windows.com",
        chrome_profile: str = "",
        pre_navigate_seconds: int = 30,
        retry_enabled: bool = True,
        retry_preset: str = "normal",
        retry_interval: float = 1.0,
        retry_max: int = 60,
    ):
        self.product_url = product_url
        self.purchase_time = purchase_time
        self.options = options
        self.quantity = quantity
        self.use_ntp = use_ntp
        self.ntp_server = ntp_server
        self.chrome_profile = chrome_profile
        self.pre_navigate_seconds = pre_navigate_seconds

        # 재시도 설정
        self.retry_enabled = retry_enabled
        if retry_preset in RETRY_PRESETS:
            preset = RETRY_PRESETS[retry_preset]
            self.retry_interval = preset["interval"]
            self.retry_max = preset["max_retries"]
        else:
            self.retry_interval = retry_interval
            self.retry_max = min(retry_max, MAX_RETRY_HARDCAP)

        if use_ntp:
            self.ntp = NTPSync(ntp_server)

        self.browser.reset_purchase_flag()
        self._stop_event.clear()

    def start(self):
        if not self._stop_event.is_set() and self._thread and self._thread.is_alive():
            self.log("이미 실행 중입니다.")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self.log("스케줄러 중지됨")

    def _run(self):
        try:
            self._execute()
        except InterruptedError:
            self.log("사용자에 의해 중지됨")
        except Exception as e:
            self.log(f"오류 발생: {e}")
            import traceback
            self.log(traceback.format_exc())
        finally:
            # M3 수정: 리소스 정리 (Chrome 프로세스는 유지 — 사용자가 확인할 수 있도록)
            if self.on_complete:
                self.on_complete()

    def _check_running(self):
        if self._stop_event.is_set():
            raise InterruptedError("사용자 중지")

    def _countdown_cb(self, remaining):
        self._check_running()
        if self.on_countdown:
            self.on_countdown(remaining)

    def _execute(self):
        # ── 1. NTP 동기화 ──
        if self.use_ntp:
            try:
                offset = self.ntp.sync()
                self.log(f"NTP 동기화 완료 (서버: {self.ntp.ntp_server}, 오프셋: {offset*1000:.1f}ms)")
            except ConnectionError as e:
                self.log(f"NTP 실패, 로컬 시간 사용: {e}")

        # ── 2. Chrome 연결 (이미 연결되어 있으면 재사용) ──
        if self.browser.driver is not None:
            self.log("기존 Chrome 세션 재사용")
        else:
            self.log("Chrome 연결 시도...")
            self.browser.launch_chrome(self.chrome_profile)
            self.browser.connect()

        # ── 3. 로그인 확인 ──
        if not self.browser.ensure_logged_in():
            self.log("로그인 실패 — 브라우저에서 수동 로그인 후 다시 시도하세요")
            return

        # ── 4. 사전 네비게이션 대기 ──
        now = self.ntp.now() if self.use_ntp else datetime.now()
        seconds_until = (self.purchase_time - now).total_seconds()

        if seconds_until > self.pre_navigate_seconds:
            pre_time = self.purchase_time - timedelta(seconds=self.pre_navigate_seconds)
            self.log(f"페이지 이동 대기... ({pre_time.strftime('%H:%M:%S')}에 이동)")
            self.ntp.wait_until(pre_time, callback=self._countdown_cb)

        self._check_running()

        # ── 5. 상품 페이지 이동 ──
        self.browser.navigate(self.product_url)
        self.log("상품 페이지 로드 완료")

        _time.sleep(1)
        current_url = self.browser.driver.current_url
        if "login" in current_url.lower():
            self.log("로그인 리다이렉트 감지 — 재로그인...")
            if not self.browser.login():
                self.log("재로그인 실패")
                return
            self.browser.navigate(self.product_url)
            _time.sleep(1)

        self.log("구매 시간 대기 중...")

        # ── 6. 구매 시간까지 대기 ──
        self.ntp.wait_until(self.purchase_time, callback=self._countdown_cb)
        self._check_running()

        # ── 7. 구매 실행 (재시도 포함) ──
        self.log("=" * 40)
        self.log("구매 시작!")
        self.log("=" * 40)

        if self.retry_enabled:
            self._execute_with_retry()
        else:
            self._execute_single_attempt()

    def _execute_single_attempt(self):
        """단일 구매 시도"""
        self.browser.driver.refresh()
        _time.sleep(0.5)
        self._do_purchase()

    def _execute_with_retry(self):
        """재시도 루프 — 품절/미오픈 시 반복"""
        for attempt in range(1, self.retry_max + 1):
            self._check_running()

            if self.on_retry_update:
                self.on_retry_update(attempt, self.retry_max, "재시도 중")

            self.log(f"[시도 {attempt}/{self.retry_max}] 페이지 새로고침...")
            self.browser.driver.refresh()
            _time.sleep(0.5)

            # 구매 가능 여부 확인
            if self.browser.is_product_available():
                self.log(f"[시도 {attempt}] 상품 구매 가능! 구매 진행...")
                if self._do_purchase():
                    if self.on_retry_update:
                        self.on_retry_update(attempt, self.retry_max, "성공")
                    return
                else:
                    self.log(f"[시도 {attempt}] 구매 버튼 클릭 실패, 재시도...")
            else:
                self.log(f"[시도 {attempt}] 품절/미오픈 상태")

            # 다음 시도까지 대기 (지터 추가)
            jitter = random.uniform(-self.retry_jitter, self.retry_jitter)
            wait = max(0.1, self.retry_interval + jitter)
            _time.sleep(wait)

        self.log(f"최대 재시도 횟수({self.retry_max})를 초과했습니다.")
        if self.on_retry_update:
            self.on_retry_update(self.retry_max, self.retry_max, "실패")

    def _do_purchase(self) -> bool:
        """실제 구매 프로세스: 옵션 → 수량 → 구매 → 결제"""
        # 옵션 선택 (텍스트 또는 번호)
        for i in range(1, 4):
            opt_val = self.options.get(f"option{i}")
            if opt_val and opt_val.strip():
                self.browser.select_option_by_text(opt_val.strip(), i)
                _time.sleep(0.3)

        # 수량
        self.browser.set_quantity(self.quantity)

        # 구매 버튼
        if self.browser.click_buy_button():
            _time.sleep(1)
            self.browser.process_payment()
            self.log("=" * 40)
            self.log("구매 프로세스 완료!")
            self.log("=" * 40)
            # 사운드 알림
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass
            return True
        return False

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self._stop_event.is_set()
