# -*- coding: utf-8 -*-
"""NTP 시간 동기화 모듈 — ms 단위 정밀 스케줄링"""

import time
import ntplib
from datetime import datetime, timedelta


class NTPSync:
    """NTP 서버와의 시간 오프셋을 계산하고 정밀 대기를 수행"""

    FALLBACK_SERVERS = [
        "time.windows.com",
        "pool.ntp.org",
        "time.google.com",
        "time.cloudflare.com",
        "ntp.ubuntu.com",
    ]

    MAX_WAIT_SECONDS = 86400  # 24시간 안전 밸브

    def __init__(self, ntp_server: str = "time.windows.com"):
        self.ntp_server = ntp_server
        self.offset: float = 0.0
        self._synced = False

    def sync(self) -> float:
        """NTP 동기화. 실패 시 fallback 서버 자동 시도."""
        servers = [self.ntp_server] + [
            s for s in self.FALLBACK_SERVERS if s != self.ntp_server
        ]
        last_error = None
        client = ntplib.NTPClient()
        for server in servers:
            try:
                response = client.request(server, version=3, timeout=3)
                self.offset = response.offset
                self._synced = True
                self.ntp_server = server
                return self.offset
            except Exception as e:
                last_error = e
                continue
        self._synced = False
        self.offset = 0.0
        raise ConnectionError(f"모든 NTP 서버 실패 (마지막: {last_error})")

    def now(self) -> datetime:
        """보정된 현재 시간"""
        return datetime.now() + timedelta(seconds=self.offset)

    def wait_until(self, target: datetime, callback=None) -> bool:
        """target 시각까지 정밀 대기.

        3단계: >2초 sleep(0.5) → 0.1~2초 sleep(0.01) → <0.1초 busy-wait
        안전 밸브: 24시간 초과 시 자동 종료
        """
        start = time.monotonic()
        while True:
            now = self.now()
            remaining = (target - now).total_seconds()

            # 안전 밸브
            if time.monotonic() - start > self.MAX_WAIT_SECONDS:
                return False

            if callback:
                callback(remaining)

            if remaining <= 0:
                return True

            if remaining > 2.0:
                time.sleep(0.5)
            elif remaining > 0.1:
                time.sleep(0.01)
            else:
                time.sleep(0.001)  # busy-wait에서도 최소 1ms sleep (CPU 보호)

    @property
    def is_synced(self) -> bool:
        return self._synced

    @property
    def offset_ms(self) -> float:
        return self.offset * 1000
