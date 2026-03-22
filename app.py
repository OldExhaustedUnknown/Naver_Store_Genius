# -*- coding: utf-8 -*-
"""
Naver Store Genius — 네이버 스마트스토어 자동 구매
CustomTkinter / 네이버 스마트스토어 공식 디자인 시스템 적용
"""

import json
import os
import time
import threading
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from scheduler import PurchaseScheduler, RETRY_PRESETS
from datetime_picker import CalendarPopup, TimeSpinbox
from browser import (
    save_credentials, load_credentials, delete_credentials,
    save_api_key, load_api_key, delete_api_key,
    validate_smartstore_url, BrowserManager,
)

# ══════════════════════════════════════════════
#  네이버 스마트스토어 공식 디자인 시스템
# ══════════════════════════════════════════════
T = {
    # Primary brand
    "primary": "#03C75A",
    "primary_hover": "#00942D",
    "primary_dark": "#00AE34",
    # Text
    "text_dark": "#121212",
    "text_primary": "#303236",
    "text_secondary": "#4D5159",
    "text_tertiary": "#767A83",
    "text_hint": "#8F95A0",
    # Background
    "bg_white": "#FFFFFF",
    "bg_page": "#F8F9FD",
    "bg_light": "#FAFAFA",
    "bg_section": "#EDF0F5",
    # Border
    "border_default": "#DBDDE2",
    "border_card": "#E3E7EE",
    "border_input": "#E9EBF0",
    # Status
    "danger": "#FF545C",
    "danger_hover": "#FF3A35",
    "warning": "#FF7200",
    "info": "#1088ED",
    "success": "#03C75A",
    # Countdown
    "countdown_normal": "#303236",
    "countdown_near": "#FF7200",
    "countdown_go": "#FF545C",
}

FONT_FAMILY = "Malgun Gothic"
FONT_MONO = "Consolas"

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("green")

CONFIG_PATH = Path(__file__).parent / "config.json"


class AutoBuyerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Naver Store Genius")
        self.geometry("760x960")
        self.resizable(False, False)
        self.configure(fg_color=T["bg_page"])
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.scheduler = PurchaseScheduler(log_callback=self._log)
        self.scheduler.on_countdown = self._update_countdown
        self.scheduler.on_complete = self._on_complete
        self.scheduler.on_retry_update = self._on_retry_update

        self._build_ui()
        self._load_config()
        self._load_saved_credentials()

    # ══════════════════════════════════════════════
    #  UI 헬퍼
    # ══════════════════════════════════════════════

    def _card(self, parent, **kwargs) -> ctk.CTkFrame:
        """네이버 스타일 카드 프레임"""
        return ctk.CTkFrame(
            parent,
            fg_color=T["bg_white"],
            border_color=T["border_card"],
            border_width=1,
            corner_radius=12,
            **kwargs,
        )

    def _section_title(self, parent, text: str):
        ctk.CTkLabel(
            parent, text=text,
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
            text_color=T["text_dark"],
        ).pack(anchor="w", padx=18, pady=(14, 6))

    def _label(self, parent, text: str, width: int = 90) -> ctk.CTkLabel:
        return ctk.CTkLabel(
            parent, text=text, width=width, anchor="w",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            text_color=T["text_secondary"],
        )

    def _entry(self, parent, placeholder: str = "", width: int = 0, **kwargs) -> ctk.CTkEntry:
        e = ctk.CTkEntry(
            parent, placeholder_text=placeholder,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            fg_color=T["bg_white"],
            border_color=T["border_input"],
            text_color=T["text_primary"],
            placeholder_text_color=T["text_hint"],
            corner_radius=8,
            **({"width": width} if width else {}),
            **kwargs,
        )
        return e

    def _btn_primary(self, parent, text: str, command, **kwargs) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent, text=text, command=command,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            fg_color=T["primary"], hover_color=T["primary_hover"],
            text_color="#FFFFFF", corner_radius=8, height=42,
            **kwargs,
        )

    def _btn_secondary(self, parent, text: str, command, **kwargs) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent, text=text, command=command,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            fg_color=T["bg_white"], hover_color=T["bg_section"],
            text_color=T["text_secondary"],
            border_color=T["border_default"], border_width=1,
            corner_radius=8, height=38,
            **kwargs,
        )

    def _btn_danger(self, parent, text: str, command, **kwargs) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent, text=text, command=command,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            fg_color=T["danger"], hover_color=T["danger_hover"],
            text_color="#FFFFFF", corner_radius=8, height=42,
            **kwargs,
        )

    # ══════════════════════════════════════════════
    #  UI 구성
    # ══════════════════════════════════════════════

    def _build_ui(self):
        main = ctk.CTkScrollableFrame(
            self, fg_color=T["bg_page"],
            scrollbar_button_color=T["border_default"],
        )
        main.pack(fill="both", expand=True, padx=0, pady=0)

        # ── 헤더 ──
        header = ctk.CTkFrame(main, fg_color=T["primary"], corner_radius=0, height=56)
        header.pack(fill="x", padx=0, pady=0)
        header.pack_propagate(False)

        ctk.CTkLabel(
            header, text="  Naver Store Genius",
            font=ctk.CTkFont(family=FONT_FAMILY, size=20, weight="bold"),
            text_color="#FFFFFF",
        ).pack(side="left", padx=16)

        self.status_label = ctk.CTkLabel(
            header, text="대기 중",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            text_color="#FFFFFF",
            fg_color=T["primary_dark"],
            corner_radius=12,
            width=80, height=28,
        )
        self.status_label.pack(side="right", padx=16)

        # ── 카운트다운 카드 ──
        cd_card = self._card(main)
        cd_card.pack(fill="x", padx=16, pady=(12, 6))

        self.countdown_label = ctk.CTkLabel(
            cd_card, text="00:00:00.000",
            font=ctk.CTkFont(family=FONT_MONO, size=52, weight="bold"),
            text_color=T["countdown_normal"],
        )
        self.countdown_label.pack(pady=(16, 4))

        self.retry_label = ctk.CTkLabel(
            cd_card, text="",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=T["text_tertiary"],
        )
        self.retry_label.pack(pady=(0, 2))

        self.progress_bar = ctk.CTkProgressBar(
            cd_card, height=4,
            progress_color=T["primary"],
            fg_color=T["bg_section"],
        )
        self.progress_bar.pack(fill="x", padx=24, pady=(0, 14))
        self.progress_bar.set(0)

        # ── 로그인 카드 ──
        login_card = self._card(main)
        login_card.pack(fill="x", padx=16, pady=6)

        self._section_title(login_card, "네이버 계정")

        id_row = ctk.CTkFrame(login_card, fg_color="transparent")
        id_row.pack(fill="x", padx=18, pady=3)
        self._label(id_row, "아이디").pack(side="left")
        self.naver_id_entry = self._entry(id_row, placeholder="네이버 아이디")
        self.naver_id_entry.pack(side="left", fill="x", expand=True, padx=(4, 0))

        pw_row = ctk.CTkFrame(login_card, fg_color="transparent")
        pw_row.pack(fill="x", padx=18, pady=3)
        self._label(pw_row, "비밀번호").pack(side="left")
        self.naver_pw_entry = self._entry(pw_row, placeholder="비밀번호", show="*")
        self.naver_pw_entry.pack(side="left", fill="x", expand=True, padx=(4, 0))

        cred_row = ctk.CTkFrame(login_card, fg_color="transparent")
        cred_row.pack(fill="x", padx=18, pady=(6, 4))

        self._btn_primary(cred_row, "저장 및 로그인 확인", self._save_and_verify, width=180).pack(side="left")
        self._btn_secondary(cred_row, "자격증명 삭제", self._delete_credentials, width=120).pack(side="left", padx=(8, 0))

        self.cred_status = ctk.CTkLabel(
            cred_row, text="",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
        )
        self.cred_status.pack(side="left", padx=12)

        self.login_badge = ctk.CTkLabel(
            login_card, text="",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            height=28,
        )
        self.login_badge.pack(anchor="w", padx=18, pady=(0, 6))

        # API 키 (캡챠 자동 풀이용)
        ctk.CTkLabel(
            login_card, text="캡챠 자동 풀이 (Claude API)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color=T["text_secondary"],
        ).pack(anchor="w", padx=18, pady=(4, 2))

        api_row = ctk.CTkFrame(login_card, fg_color="transparent")
        api_row.pack(fill="x", padx=18, pady=(0, 4))
        self._label(api_row, "API Key", width=70).pack(side="left")
        self.api_key_entry = self._entry(api_row, placeholder="sk-ant-...", show="*")
        self.api_key_entry.pack(side="left", fill="x", expand=True, padx=(4, 0))

        api_btn_row = ctk.CTkFrame(login_card, fg_color="transparent")
        api_btn_row.pack(fill="x", padx=18, pady=(0, 12))
        self._btn_secondary(api_btn_row, "API 키 저장", self._save_api_key, width=110).pack(side="left")
        self._btn_secondary(api_btn_row, "삭제", self._delete_api_key, width=60).pack(side="left", padx=(6, 0))
        self.api_status = ctk.CTkLabel(
            api_btn_row, text="",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
        )
        self.api_status.pack(side="left", padx=10)

        # ── 상품 정보 카드 ──
        prod_card = self._card(main)
        prod_card.pack(fill="x", padx=16, pady=6)

        self._section_title(prod_card, "상품 정보")

        # URL + 히스토리 드롭다운
        url_row = ctk.CTkFrame(prod_card, fg_color="transparent")
        url_row.pack(fill="x", padx=18, pady=3)
        self._label(url_row, "상품 URL").pack(side="left")

        self.url_history: list[str] = []
        self.url_combo = ctk.CTkComboBox(
            url_row, values=[], width=340,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            fg_color=T["bg_white"], border_color=T["border_input"],
            text_color=T["text_primary"], button_color=T["border_default"],
            dropdown_fg_color=T["bg_white"], dropdown_text_color=T["text_primary"],
            corner_radius=8,
        )
        self.url_combo.pack(side="left", fill="x", expand=True, padx=(4, 4))
        self.url_combo.set("")

        self._btn_secondary(url_row, "미리보기", self._preview_product, width=70).pack(side="left", padx=(0, 2))
        self._btn_primary(url_row, "옵션 가져오기", self._fetch_options, width=95).pack(side="left")

        # 날짜
        date_row = ctk.CTkFrame(prod_card, fg_color="transparent")
        date_row.pack(fill="x", padx=18, pady=3)
        self._label(date_row, "구매 날짜").pack(side="left")

        self.date_entry = self._entry(date_row, placeholder="2026-03-25", width=120)
        self.date_entry.pack(side="left", padx=(4, 4))
        self._btn_secondary(date_row, "달력", self._open_calendar, width=50).pack(side="left")

        # 시간 + 프리셋
        time_row = ctk.CTkFrame(prod_card, fg_color="transparent")
        time_row.pack(fill="x", padx=18, pady=3)
        self._label(time_row, "구매 시간").pack(side="left")

        self.time_spinbox = TimeSpinbox(time_row, font_family=FONT_FAMILY)
        self.time_spinbox.pack(side="left", padx=(4, 8))

        # 시간 프리셋 버튼
        presets_frame = ctk.CTkFrame(time_row, fg_color="transparent")
        presets_frame.pack(side="left")
        for h in [10, 11, 12, 14, 20]:
            ctk.CTkButton(
                presets_frame, text=f"{h}시", width=38, height=26,
                fg_color=T["bg_section"], hover_color=T["border_default"],
                text_color=T["text_secondary"], corner_radius=6,
                font=ctk.CTkFont(family=FONT_FAMILY, size=11),
                command=lambda hh=h: self.time_spinbox.set_values(hh, 0, 0),
            ).pack(side="left", padx=1)

        qty_row = ctk.CTkFrame(prod_card, fg_color="transparent")
        qty_row.pack(fill="x", padx=18, pady=(3, 12))
        self._label(qty_row, "수량").pack(side="left")
        self.qty_entry = self._entry(qty_row, placeholder="1", width=65)
        self.qty_entry.pack(side="left", padx=(4, 0))
        self.qty_entry.insert(0, "1")

        # ── 옵션 카드 ──
        opt_card = self._card(main)
        opt_card.pack(fill="x", padx=16, pady=6)

        opt_header = ctk.CTkFrame(opt_card, fg_color="transparent")
        opt_header.pack(fill="x", padx=18, pady=(14, 2))
        ctk.CTkLabel(
            opt_header, text="옵션 선택",
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
            text_color=T["text_dark"],
        ).pack(side="left")
        ctk.CTkLabel(
            opt_header, text="  '옵션 가져오기'로 자동 추출하거나 직접 입력",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=T["text_hint"],
        ).pack(side="left")

        self.options_container = ctk.CTkFrame(opt_card, fg_color="transparent")
        self.options_container.pack(fill="x", padx=18, pady=(4, 12))

        # 기본 3개 옵션 (ComboBox — 드롭다운 + 직접 입력)
        self.option_combos: list[ctk.CTkComboBox] = []
        self.option_labels: list[ctk.CTkLabel] = []
        for i in range(3):
            row = ctk.CTkFrame(self.options_container, fg_color="transparent")
            row.pack(fill="x", pady=2)
            lbl = ctk.CTkLabel(
                row, text=f"옵션 {i+1}", width=80, anchor="w",
                font=ctk.CTkFont(family=FONT_FAMILY, size=13),
                text_color=T["text_secondary"],
            )
            lbl.pack(side="left")
            combo = ctk.CTkComboBox(
                row, values=[], width=250,
                font=ctk.CTkFont(family=FONT_FAMILY, size=13),
                fg_color=T["bg_white"], border_color=T["border_input"],
                text_color=T["text_primary"], button_color=T["border_default"],
                dropdown_fg_color=T["bg_white"], dropdown_text_color=T["text_primary"],
                corner_radius=8,
            )
            combo.pack(side="left", padx=(4, 0))
            combo.set("")
            self.option_combos.append(combo)
            self.option_labels.append(lbl)

        # ── 재시도 설정 카드 ──
        retry_card = self._card(main)
        retry_card.pack(fill="x", padx=16, pady=6)

        self._section_title(retry_card, "재시도 설정")
        ctk.CTkLabel(
            retry_card,
            text="오픈 시간에 품절/미오픈일 경우 자동으로 재시도합니다.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=T["text_hint"],
        ).pack(anchor="w", padx=18, pady=(0, 6))

        retry_toggle_row = ctk.CTkFrame(retry_card, fg_color="transparent")
        retry_toggle_row.pack(fill="x", padx=18, pady=3)

        self.retry_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(
            retry_toggle_row, text="재시도 모드",
            variable=self.retry_var,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            text_color=T["text_primary"],
            progress_color=T["primary"],
            button_color=T["primary"],
        ).pack(side="left")

        retry_preset_row = ctk.CTkFrame(retry_card, fg_color="transparent")
        retry_preset_row.pack(fill="x", padx=18, pady=3)
        self._label(retry_preset_row, "프리셋", width=60).pack(side="left")
        self.retry_preset_var = ctk.StringVar(value="normal")
        presets = ["빠름 (0.5초)", "보통 (1초)", "안전 (2초)"]
        self.retry_preset_menu = ctk.CTkSegmentedButton(
            retry_preset_row,
            values=presets,
            command=self._on_retry_preset_change,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            selected_color=T["primary"],
            selected_hover_color=T["primary_hover"],
            unselected_color=T["bg_white"],
            unselected_hover_color=T["bg_section"],
            text_color=T["text_primary"],
            text_color_disabled=T["text_hint"],
        )
        self.retry_preset_menu.pack(side="left", padx=(4, 0))
        self.retry_preset_menu.set("보통 (1초)")

        retry_custom_row = ctk.CTkFrame(retry_card, fg_color="transparent")
        retry_custom_row.pack(fill="x", padx=18, pady=(3, 12))
        self._label(retry_custom_row, "간격(초)", width=60).pack(side="left")
        self.retry_interval_entry = self._entry(retry_custom_row, placeholder="1.0", width=60)
        self.retry_interval_entry.pack(side="left", padx=(4, 12))
        self.retry_interval_entry.insert(0, "1.0")

        self._label(retry_custom_row, "최대횟수", width=60).pack(side="left")
        self.retry_max_entry = self._entry(retry_custom_row, placeholder="60", width=60)
        self.retry_max_entry.pack(side="left", padx=(4, 0))
        self.retry_max_entry.insert(0, "60")

        # ── 고급 설정 카드 ──
        adv_card = self._card(main)
        adv_card.pack(fill="x", padx=16, pady=6)

        self._section_title(adv_card, "고급 설정")

        adv_grid = ctk.CTkFrame(adv_card, fg_color="transparent")
        adv_grid.pack(fill="x", padx=18, pady=(0, 12))

        self.ntp_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            adv_grid, text="NTP 시간 동기화",
            variable=self.ntp_var,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            text_color=T["text_primary"],
            checkmark_color="#FFFFFF",
            fg_color=T["primary"],
            hover_color=T["primary_hover"],
        ).grid(row=0, column=0, sticky="w", pady=3)

        self._label(adv_grid, "사전 이동(초)", width=90).grid(row=1, column=0, sticky="w", pady=3)
        self.pre_nav_entry = self._entry(adv_grid, width=60)
        self.pre_nav_entry.grid(row=1, column=1, sticky="w", padx=4, pady=3)
        self.pre_nav_entry.insert(0, "30")

        self._label(adv_grid, "Chrome 프로필", width=90).grid(row=2, column=0, sticky="w", pady=3)
        self.profile_entry = self._entry(adv_grid, placeholder="비워두면 기본값", width=280)
        self.profile_entry.grid(row=2, column=1, columnspan=3, sticky="w", padx=4, pady=3)

        # ── 버튼 ──
        btn_frame = ctk.CTkFrame(main, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=10)

        self._btn_primary(btn_frame, "스케줄 추가", self._add_schedule, width=120).pack(side="left", padx=(0, 4))
        self.start_all_btn = self._btn_primary(btn_frame, "전체 시작", self._start_all)
        self.start_all_btn.pack(side="left", expand=True, fill="x", padx=4)
        self.stop_all_btn = self._btn_danger(btn_frame, "전체 중지", self._stop_all, state="disabled")
        self.stop_all_btn.pack(side="left", expand=True, fill="x", padx=4)
        self.save_btn = self._btn_secondary(btn_frame, "설정 저장", self._save_config)
        self.save_btn.pack(side="left", expand=True, fill="x", padx=(4, 0))

        # ── 스케줄 리스트 카드 ──
        sched_card = self._card(main)
        sched_card.pack(fill="x", padx=16, pady=6)

        self._section_title(sched_card, "스케줄 목록")

        self.schedule_list_frame = ctk.CTkFrame(sched_card, fg_color="transparent")
        self.schedule_list_frame.pack(fill="x", padx=18, pady=(0, 12))

        # 헤더
        hdr = ctk.CTkFrame(self.schedule_list_frame, fg_color=T["bg_section"], corner_radius=6)
        hdr.pack(fill="x", pady=(0, 4))
        for text, w in [("상품", 200), ("시간", 100), ("수량", 40), ("옵션", 100), ("상태", 70), ("", 60)]:
            ctk.CTkLabel(
                hdr, text=text, width=w,
                font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
                text_color=T["text_tertiary"],
            ).pack(side="left", padx=4, pady=4)

        self.schedule_rows_frame = ctk.CTkFrame(self.schedule_list_frame, fg_color="transparent")
        self.schedule_rows_frame.pack(fill="x")

        # 스케줄 데이터 저장소
        self.schedules: list[dict] = []

        # ── 로그 카드 ──
        log_card = self._card(main)
        log_card.pack(fill="both", expand=True, padx=16, pady=(6, 12))

        self._section_title(log_card, "실행 로그")

        self.log_box = ctk.CTkTextbox(
            log_card,
            font=ctk.CTkFont(family=FONT_MONO, size=11),
            fg_color=T["bg_light"],
            text_color=T["text_primary"],
            border_color=T["border_input"],
            border_width=1,
            corner_radius=8,
            state="disabled",
            height=140,
        )
        self.log_box.pack(fill="both", expand=True, padx=18, pady=(0, 14))

    # ══════════════════════════════════════════════
    #  로그인 / 자격증명
    # ══════════════════════════════════════════════

    def _save_and_verify(self):
        """자격증명 저장 → 실제 Chrome으로 네이버 로그인 확인 → 성공 시 최소화"""
        nid = self.naver_id_entry.get().strip()
        npw = self.naver_pw_entry.get().strip()
        if not nid or not npw:
            self.cred_status.configure(text="ID/PW를 입력하세요", text_color=T["danger"])
            return

        # 저장
        save_credentials(nid, npw)
        self.naver_pw_entry.delete(0, "end")
        self.cred_status.configure(text="저장 완료, Chrome 실행 중...", text_color=T["info"])
        self._log("자격증명 저장 완료. Chrome을 열어 로그인을 확인합니다...")

        # 스케줄러의 browser 인스턴스를 재사용 (나중에 예약 시에도 같은 Chrome 사용)
        profile = self.profile_entry.get().strip()

        def verify():
            browser = self.scheduler.browser
            try:
                # 1+2. Chrome 실행 및 연결 (이미 연결되어 있으면 재사용)
                if browser.driver is not None:
                    self._log("기존 Chrome 세션 재사용")
                    try:
                        browser.driver.title  # 연결 유효성 확인
                    except Exception:
                        self._log("기존 세션 끊김 — 재연결...")
                        browser.driver = None

                if browser.driver is None:
                    self._log("[1/4] Chrome 실행 중...")
                    browser.launch_chrome(profile)
                    self._log("[2/4] Chrome 연결 중...")
                    browser.connect()
                    self._log("[2/4] Chrome 연결 성공")

                # 3. 네이버 로그인 페이지로 이동
                self._log("[3/4] 네이버 로그인 상태 확인 중...")
                if browser.is_logged_in():
                    self._log("[4/4] 이미 로그인되어 있습니다!")
                    self.after(0, lambda: self._set_login_badge(True))
                    browser.minimize_window()
                    return

                # 4. 로그인 시도
                self._log("[3/4] 로그인 필요 — 네이버 로그인 페이지로 이동합니다...")
                self._log("[4/4] 로그인 시도 중...")
                if browser.login(nid, npw):
                    self._log("로그인 확인 성공! Chrome을 최소화합니다.")
                    self.after(0, lambda: self._set_login_badge(True))
                    browser.minimize_window()
                else:
                    self._log("로그인 실패. ID/PW를 확인하거나 브라우저에서 직접 로그인하세요.")
                    self.after(0, lambda: self._set_login_badge(False))
            except Exception as e:
                self._log(f"로그인 확인 오류: {e}")
                import traceback
                self._log(traceback.format_exc())
                self.after(0, lambda: self._set_login_badge(False))

        threading.Thread(target=verify, daemon=True).start()

    def _set_login_badge(self, success: bool):
        if success:
            self.login_badge.configure(
                text="  로그인 확인됨  ",
                text_color="#FFFFFF",
                fg_color=T["primary"],
                corner_radius=12,
            )
            self.cred_status.configure(text="", text_color=T["text_hint"])
        else:
            self.login_badge.configure(
                text="  로그인 실패  ",
                text_color="#FFFFFF",
                fg_color=T["danger"],
                corner_radius=12,
            )
            self.cred_status.configure(text="ID/PW 확인 필요", text_color=T["danger"])

    def _delete_credentials(self):
        delete_credentials()
        self.naver_id_entry.delete(0, "end")
        self.naver_pw_entry.delete(0, "end")
        self.login_badge.configure(text="", fg_color="transparent")
        self.cred_status.configure(text="삭제 완료", text_color=T["warning"])
        self._log("자격증명이 삭제되었습니다.")

    def _save_api_key(self):
        key = self.api_key_entry.get().strip()
        if not key:
            self.api_status.configure(text="API 키를 입력하세요", text_color=T["danger"])
            return
        save_api_key(key)
        self.api_key_entry.delete(0, "end")
        self.api_key_entry.insert(0, "*" * 20)
        self.api_status.configure(text="저장 완료", text_color=T["primary"])
        self._log("Claude API 키가 저장되었습니다. (캡챠 자동 풀이 활성화)")

    def _delete_api_key(self):
        delete_api_key()
        self.api_key_entry.delete(0, "end")
        self.api_status.configure(text="삭제됨", text_color=T["warning"])
        self._log("API 키가 삭제되었습니다.")

    def _open_calendar(self):
        """달력 팝업 열기"""
        def on_select(date_str):
            self.date_entry.delete(0, "end")
            self.date_entry.insert(0, date_str)

        try:
            current = datetime.strptime(self.date_entry.get().strip(), "%Y-%m-%d")
        except (ValueError, AttributeError):
            current = datetime.now()

        CalendarPopup(self, on_select, current_date=current)

    def _preview_product(self):
        """상품 URL을 Chrome에서 미리 열어 옵션/상태 확인"""
        url = self.url_combo.get().strip()
        if not url:
            self._log("상품 URL을 입력하세요.")
            return

        profile = self.profile_entry.get().strip()

        def _open():
            browser = self.scheduler.browser
            try:
                if browser.driver is not None:
                    try:
                        browser.driver.title
                    except Exception:
                        browser.driver = None

                if browser.driver is None:
                    browser.launch_chrome(profile)
                    browser.connect()

                browser.navigate(url)
                browser.restore_window()
                self._log(f"상품 페이지 열림: {url[:50]}...")
            except Exception as e:
                self._log(f"미리보기 오류: {e}")

        threading.Thread(target=_open, daemon=True).start()

    def _fetch_options(self):
        """상품 페이지에서 옵션을 자동 추출하여 드롭다운에 반영"""
        url = self.url_combo.get().strip()
        if not url:
            self._log("상품 URL을 입력하세요.")
            return

        self._log(f"옵션 추출 중: {url[:50]}...")
        profile = self.profile_entry.get().strip()

        def _extract():
            browser = self.scheduler.browser
            try:
                if browser.driver is not None:
                    try:
                        browser.driver.title
                    except Exception:
                        browser.driver = None

                if browser.driver is None:
                    browser.launch_chrome(profile)
                    browser.connect()

                browser.navigate(url)
                time.sleep(1)

                options = browser.extract_product_options()

                # GUI 업데이트 (메인 스레드에서)
                def _update_ui():
                    for i, combo in enumerate(self.option_combos):
                        combo.configure(values=[])
                        combo.set("")
                        self.option_labels[i].configure(text=f"옵션 {i+1}")

                    for i, opt in enumerate(options[:3]):
                        self.option_labels[i].configure(text=opt["name"])
                        self.option_combos[i].configure(values=opt["values"])
                        if opt["values"]:
                            self.option_combos[i].set(opt["values"][0])

                    if options:
                        self._log(f"옵션 {len(options)}개 추출: " +
                                  ", ".join(f'{o["name"]}({len(o["values"])}개)' for o in options))
                    else:
                        self._log("추출 가능한 옵션이 없습니다.")

                self.after(0, _update_ui)
                browser.minimize_window()

            except Exception as e:
                self._log(f"옵션 추출 오류: {e}")

        threading.Thread(target=_extract, daemon=True).start()

    def _load_saved_credentials(self):
        nid, _ = load_credentials()
        if nid:
            self.naver_id_entry.insert(0, nid)
            self.cred_status.configure(text="자격증명 저장됨 (확인 필요)", text_color=T["text_tertiary"])
        # API 키 상태
        api_key = load_api_key()
        if api_key:
            self.api_key_entry.insert(0, "*" * 20)
            self.api_status.configure(text="API 키 저장됨", text_color=T["primary"])

    # ══════════════════════════════════════════════
    #  재시도 프리셋
    # ══════════════════════════════════════════════

    def _on_retry_preset_change(self, value: str):
        preset_map = {"빠름 (0.5초)": "fast", "보통 (1초)": "normal", "안전 (2초)": "safe"}
        key = preset_map.get(value, "normal")
        preset = RETRY_PRESETS[key]
        self.retry_interval_entry.delete(0, "end")
        self.retry_interval_entry.insert(0, str(preset["interval"]))
        self.retry_max_entry.delete(0, "end")
        self.retry_max_entry.insert(0, str(preset["max_retries"]))

    # ══════════════════════════════════════════════
    #  이벤트 핸들러
    # ══════════════════════════════════════════════

    def _collect_form_data(self) -> dict | None:
        """현재 폼에서 스케줄 데이터 수집"""
        url = self.url_combo.get().strip()
        if not url:
            self._log("상품 URL을 입력하세요.")
            return None

        try:
            date_str = self.date_entry.get().strip()
            h, m, s = self.time_spinbox.get_values()
            purchase_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=h, minute=m, second=s)
        except (ValueError, AttributeError):
            self._log("구매 일시 형식 오류 (YYYY-MM-DD)")
            return None

        if purchase_dt <= datetime.now():
            self._log(f"구매 시간이 과거입니다: {purchase_dt}")
            return None

        try:
            qty = int(self.qty_entry.get().strip() or "1")
        except ValueError:
            self._log("수량은 숫자여야 합니다.")
            return None
        if qty < 1 or qty > 99:
            self._log("수량은 1~99 사이여야 합니다.")
            return None

        options = {}
        opt_parts = []
        for i, combo in enumerate(self.option_combos, 1):
            val = combo.get().strip()
            options[f"option{i}"] = val if val else None
            if val:
                opt_parts.append(val)

        try:
            retry_interval = float(self.retry_interval_entry.get().strip() or "1.0")
            retry_max = int(self.retry_max_entry.get().strip() or "60")
        except ValueError:
            retry_interval = 1.0
            retry_max = 60

        return {
            "url": url,
            "purchase_dt": purchase_dt,
            "quantity": qty,
            "options": options,
            "opt_desc": ", ".join(opt_parts) if opt_parts else "",
            "retry_enabled": self.retry_var.get(),
            "retry_interval": retry_interval,
            "retry_max": retry_max,
            "status": "대기",
            "scheduler": None,
        }

    def _add_schedule(self):
        """현재 폼 데이터로 스케줄 추가"""
        data = self._collect_form_data()
        if not data:
            return
        for s in self.schedules:
            if s["url"] == data["url"] and s["purchase_dt"] == data["purchase_dt"]:
                self._log("동일 URL/시간 스케줄이 이미 있습니다.")
                return
        self.schedules.append(data)
        self._render_schedules()
        dt_str = data["purchase_dt"].strftime("%H:%M:%S")
        self._log(f"스케줄 추가: {data['url'][:40]}... @ {dt_str} x{data['quantity']}")
        # URL 히스토리
        url = data["url"]
        if url not in self.url_history:
            self.url_history.insert(0, url)
            self.url_history = self.url_history[:10]
            self.url_combo.configure(values=self.url_history)

    def _render_schedules(self):
        """스케줄 리스트 렌더링"""
        for w in self.schedule_rows_frame.winfo_children():
            w.destroy()
        for idx, sched in enumerate(self.schedules):
            row = ctk.CTkFrame(self.schedule_rows_frame, fg_color="transparent")
            row.pack(fill="x", pady=1)
            url_short = sched["url"].split("/")[-1][:25] if "/" in sched["url"] else sched["url"][:25]
            ctk.CTkLabel(row, text=url_short, width=200, anchor="w",
                font=ctk.CTkFont(family=FONT_FAMILY, size=12), text_color=T["text_primary"],
            ).pack(side="left", padx=4)
            ctk.CTkLabel(row, text=sched["purchase_dt"].strftime("%m/%d %H:%M:%S"), width=100,
                font=ctk.CTkFont(family=FONT_MONO, size=12), text_color=T["text_secondary"],
            ).pack(side="left", padx=4)
            ctk.CTkLabel(row, text=str(sched["quantity"]), width=40,
                font=ctk.CTkFont(family=FONT_FAMILY, size=12), text_color=T["text_secondary"],
            ).pack(side="left", padx=4)
            ctk.CTkLabel(row, text=sched["opt_desc"] or "-", width=100, anchor="w",
                font=ctk.CTkFont(family=FONT_FAMILY, size=11), text_color=T["text_tertiary"],
            ).pack(side="left", padx=4)
            status = sched["status"]
            sc = {"대기": T["text_hint"], "실행 중": T["primary"], "완료": T["info"], "실패": T["danger"]}.get(status, T["text_hint"])
            ctk.CTkLabel(row, text=status, width=70,
                font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"), text_color=sc,
            ).pack(side="left", padx=4)
            ctk.CTkButton(row, text="X", width=30, height=24,
                fg_color=T["bg_section"], hover_color=T["danger"],
                text_color=T["text_tertiary"], corner_radius=4, font=ctk.CTkFont(size=11),
                command=lambda i=idx: self._remove_schedule(i),
            ).pack(side="left", padx=4)
        if not self.schedules:
            ctk.CTkLabel(self.schedule_rows_frame, text="스케줄 없음 — 위에서 설정 후 '스케줄 추가' 클릭",
                font=ctk.CTkFont(family=FONT_FAMILY, size=12), text_color=T["text_hint"],
            ).pack(pady=8)

    def _remove_schedule(self, idx: int):
        if 0 <= idx < len(self.schedules):
            s = self.schedules[idx]
            if s["scheduler"] and s["scheduler"].is_running:
                s["scheduler"].stop()
            self.schedules.pop(idx)
            self._render_schedules()
            self._log(f"스케줄 {idx+1} 삭제")

    def _start_all(self):
        """모든 대기 스케줄 시작"""
        pending = [s for s in self.schedules if s["status"] == "대기"]
        if not pending:
            self._log("시작할 스케줄이 없습니다. '스케줄 추가'를 먼저 하세요.")
            return
        if not messagebox.askyesno("전체 시작", f"{len(pending)}개 스케줄 시작.\n실제 주문이 이루어집니다.", icon="warning"):
            return
        pre_nav = int(self.pre_nav_entry.get().strip() or "30")
        profile = self.profile_entry.get().strip()
        for i, sched in enumerate(pending):
            scheduler = PurchaseScheduler(log_callback=self._log)
            scheduler.on_countdown = self._update_countdown
            scheduler.on_complete = lambda s=sched: self._on_schedule_complete(s)
            if i == 0 and self.scheduler.browser.driver is not None:
                scheduler.browser = self.scheduler.browser
            scheduler.configure(
                product_url=sched["url"], purchase_time=sched["purchase_dt"],
                options=sched["options"], quantity=sched["quantity"],
                use_ntp=self.ntp_var.get(), chrome_profile=profile,
                pre_navigate_seconds=pre_nav, retry_enabled=sched["retry_enabled"],
                retry_preset="custom", retry_interval=sched["retry_interval"],
                retry_max=sched["retry_max"],
            )
            sched["scheduler"] = scheduler
            sched["status"] = "실행 중"
            scheduler.start()
        self.start_all_btn.configure(state="disabled")
        self.stop_all_btn.configure(state="normal")
        self.status_label.configure(text=f"{len(pending)}개 실행 중", fg_color=T["primary"])
        self._render_schedules()
        self._log(f"전체 시작: {len(pending)}개 스케줄")

    def _stop_all(self):
        for s in self.schedules:
            if s["scheduler"] and s["scheduler"].is_running:
                s["scheduler"].stop()
                s["status"] = "대기"
        self.start_all_btn.configure(state="normal")
        self.stop_all_btn.configure(state="disabled")
        self.status_label.configure(text="중지됨", fg_color=T["danger"])
        self.countdown_label.configure(text="00:00:00.000", text_color=T["countdown_normal"])
        self.progress_bar.set(0)
        self._render_schedules()
        self._log("전체 중지")

    def _on_schedule_complete(self, sched: dict):
        sched["status"] = "완료"
        self.after(0, self._render_schedules)
        running = [s for s in self.schedules if s["status"] == "실행 중"]
        if not running:
            def _done():
                self.start_all_btn.configure(state="normal")
                self.stop_all_btn.configure(state="disabled")
                self.status_label.configure(text="전체 완료", fg_color=T["warning"])
                self.progress_bar.set(1)
                try:
                    import winsound
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                except Exception:
                    pass
            self.after(0, _done)

    def _on_retry_update(self, current: int, max_retries: int, status: str):
        def _update():
            self.retry_label.configure(
                text=f"재시도 {current}/{max_retries} — {status}",
                text_color=T["info"] if status == "재시도 중" else (
                    T["success"] if status == "성공" else T["danger"]
                ),
            )
        self.after(0, _update)

    def _on_close(self):
        running = [s for s in self.schedules if s.get("scheduler") and s["scheduler"].is_running]
        if running:
            if not messagebox.askyesno("종료 확인", f"{len(running)}개 스케줄이 실행 중입니다. 정말 종료하시겠습니까?"):
                return
            for s in running:
                s["scheduler"].stop()
        # Chrome/chromedriver 정리
        try:
            self.scheduler.browser.quit()
        except Exception:
            pass
        for s in self.schedules:
            if s.get("scheduler") and s["scheduler"].browser:
                try:
                    s["scheduler"].browser.quit()
                except Exception:
                    pass
        self.destroy()

    # ══════════════════════════════════════════════
    #  카운트다운 & 로그
    # ══════════════════════════════════════════════

    def _update_countdown(self, remaining: float):
        self.after(0, self._set_countdown, remaining)

    def _set_countdown(self, remaining: float):
        if remaining <= 0:
            self.countdown_label.configure(text="GO!", text_color=T["countdown_go"])
            self.progress_bar.set(1)
            return

        hours = int(remaining // 3600)
        mins = int((remaining % 3600) // 60)
        secs = int(remaining % 60)
        ms = int((remaining % 1) * 1000)

        self.countdown_label.configure(text=f"{hours:02d}:{mins:02d}:{secs:02d}.{ms:03d}")

        if remaining < 5:
            self.countdown_label.configure(text_color=T["countdown_go"])
        elif remaining < 30:
            self.countdown_label.configure(text_color=T["countdown_near"])
        else:
            self.countdown_label.configure(text_color=T["countdown_normal"])

        if hasattr(self, "_total_wait") and self._total_wait > 0:
            self.progress_bar.set(max(0, min(1, 1 - remaining / self._total_wait)))

    def _log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"[{timestamp}] {message}\n"

        def _append():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", line)
            self.log_box.see("end")
            self.log_box.configure(state="disabled")

        try:
            self.after(0, _append)
        except RuntimeError:
            print(line, end="")  # m8 수정: fallback to stdout

    # ══════════════════════════════════════════════
    #  설정 저장/로드
    # ══════════════════════════════════════════════

    def _save_config(self):
        # URL 히스토리 업데이트
        url = self.url_combo.get().strip()
        if url and url not in self.url_history:
            self.url_history.insert(0, url)
            self.url_history = self.url_history[:10]  # 최대 10개
            self.url_combo.configure(values=self.url_history)

        config = {
            "product_url": url,
            "url_history": self.url_history,
            "purchase_date": self.date_entry.get().strip(),
            "purchase_hour": str(self.time_spinbox.get_values()[0]),
            "purchase_min": str(self.time_spinbox.get_values()[1]),
            "purchase_sec": str(self.time_spinbox.get_values()[2]),
            "option1": self.option_combos[0].get().strip(),
            "option2": self.option_combos[1].get().strip(),
            "option3": self.option_combos[2].get().strip(),
            "quantity": self.qty_entry.get().strip(),
            "use_ntp_sync": self.ntp_var.get(),
            "pre_navigate_seconds": self.pre_nav_entry.get().strip(),
            "chrome_profile_path": self.profile_entry.get().strip(),
            "retry_enabled": self.retry_var.get(),
            "retry_interval": self.retry_interval_entry.get().strip(),
            "retry_max": self.retry_max_entry.get().strip(),
        }
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        self._log("설정 저장 완료")

    def _load_config(self):
        if not CONFIG_PATH.exists():
            return
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return

        def _set(entry, key):
            val = config.get(key, "")
            if val:
                entry.delete(0, "end")
                entry.insert(0, str(val))

        url_val = config.get("product_url", "")
        if url_val:
            self.url_combo.set(url_val)
        # URL 히스토리 로드
        self.url_history = config.get("url_history", [])
        if self.url_history:
            self.url_combo.configure(values=self.url_history)
        _set(self.date_entry, "purchase_date")
        # 시간 스핀박스 로드
        try:
            h = int(config.get("purchase_hour", 0) or 0)
            m = int(config.get("purchase_min", 0) or 0)
            s = int(config.get("purchase_sec", 0) or 0)
            self.time_spinbox.set_values(h, m, s)
        except (ValueError, TypeError):
            pass
        for i, key in enumerate(["option1", "option2", "option3"]):
            val = config.get(key, "")
            if val:
                self.option_combos[i].set(val)
        _set(self.qty_entry, "quantity")
        _set(self.pre_nav_entry, "pre_navigate_seconds")
        _set(self.profile_entry, "chrome_profile_path")
        _set(self.retry_interval_entry, "retry_interval")
        _set(self.retry_max_entry, "retry_max")
        self.ntp_var.set(config.get("use_ntp_sync", True))
        self.retry_var.set(config.get("retry_enabled", True))


def main():
    app = AutoBuyerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
