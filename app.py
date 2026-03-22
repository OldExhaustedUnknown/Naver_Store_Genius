# -*- coding: utf-8 -*-
"""
Naver Store Genius — 네이버 스마트스토어 자동 구매
CustomTkinter / 네이버 스마트스토어 공식 디자인 시스템 적용
"""

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from scheduler import PurchaseScheduler, RETRY_PRESETS
from browser import (
    save_credentials, load_credentials, delete_credentials,
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
        self.login_badge.pack(anchor="w", padx=18, pady=(0, 12))

        # ── 상품 정보 카드 ──
        prod_card = self._card(main)
        prod_card.pack(fill="x", padx=16, pady=6)

        self._section_title(prod_card, "상품 정보")

        url_row = ctk.CTkFrame(prod_card, fg_color="transparent")
        url_row.pack(fill="x", padx=18, pady=3)
        self._label(url_row, "상품 URL").pack(side="left")
        self.url_entry = self._entry(url_row, placeholder="https://smartstore.naver.com/...")
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(4, 0))

        time_row = ctk.CTkFrame(prod_card, fg_color="transparent")
        time_row.pack(fill="x", padx=18, pady=3)
        self._label(time_row, "구매 일시").pack(side="left")

        self.date_entry = self._entry(time_row, placeholder="2026-03-25", width=120)
        self.date_entry.pack(side="left", padx=(4, 4))

        for lbl_text, attr_name in [("시", "hour_entry"), ("분", "min_entry"), ("초", "sec_entry")]:
            e = self._entry(time_row, placeholder=lbl_text[:2].upper(), width=48)
            e.pack(side="left", padx=2)
            setattr(self, attr_name, e)
            if lbl_text != "초":
                ctk.CTkLabel(time_row, text=":", text_color=T["text_tertiary"]).pack(side="left")

        qty_row = ctk.CTkFrame(prod_card, fg_color="transparent")
        qty_row.pack(fill="x", padx=18, pady=(3, 12))
        self._label(qty_row, "수량").pack(side="left")
        self.qty_entry = self._entry(qty_row, placeholder="1", width=65)
        self.qty_entry.pack(side="left", padx=(4, 0))
        self.qty_entry.insert(0, "1")

        # ── 옵션 카드 ──
        opt_card = self._card(main)
        opt_card.pack(fill="x", padx=16, pady=6)

        self._section_title(opt_card, "옵션 선택")
        ctk.CTkLabel(
            opt_card, text="해당 없으면 비워두세요. 선택할 옵션의 순번을 입력합니다.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=T["text_hint"],
        ).pack(anchor="w", padx=18, pady=(0, 4))

        opts_row = ctk.CTkFrame(opt_card, fg_color="transparent")
        opts_row.pack(fill="x", padx=18, pady=(0, 12))

        self.option_entries = []
        for i in range(3):
            self._label(opts_row, f"옵션 {i+1}", width=55).grid(row=0, column=i*2, padx=(0, 2))
            e = self._entry(opts_row, placeholder="번호", width=55)
            e.grid(row=0, column=i*2+1, padx=(0, 12))
            self.option_entries.append(e)

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

        self.start_btn = self._btn_primary(btn_frame, "예약 시작", self._on_start)
        self.start_btn.pack(side="left", expand=True, fill="x", padx=(0, 4))

        self.stop_btn = self._btn_danger(btn_frame, "중지", self._on_stop, state="disabled")
        self.stop_btn.pack(side="left", expand=True, fill="x", padx=4)

        self.save_btn = self._btn_secondary(btn_frame, "설정 저장", self._save_config)
        self.save_btn.pack(side="left", expand=True, fill="x", padx=(4, 0))

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
        """자격증명 저장 → 실제 로그인 확인 → 성공 시 Chrome 최소화"""
        nid = self.naver_id_entry.get().strip()
        npw = self.naver_pw_entry.get().strip()
        if not nid or not npw:
            self.cred_status.configure(text="ID/PW를 입력하세요", text_color=T["danger"])
            return

        # 저장
        save_credentials(nid, npw)
        self.naver_pw_entry.delete(0, "end")
        self.cred_status.configure(text="저장 완료, 로그인 확인 중...", text_color=T["info"])
        self._log("자격증명 저장됨. 로그인 확인을 시작합니다...")

        # 별도 스레드에서 로그인 확인
        def verify():
            browser = BrowserManager(log_callback=self._log)
            try:
                browser.launch_chrome(self.profile_entry.get().strip())
                browser.connect()

                if browser.is_logged_in():
                    self._log("이미 로그인 상태입니다.")
                    self.after(0, lambda: self._set_login_badge(True))
                    browser.minimize_window()
                    return

                if browser.login(nid, npw):
                    self._log("로그인 확인 성공!")
                    self.after(0, lambda: self._set_login_badge(True))
                    browser.minimize_window()
                else:
                    self._log("로그인 실패. ID/PW를 확인해주세요.")
                    self.after(0, lambda: self._set_login_badge(False))
            except Exception as e:
                self._log(f"로그인 확인 오류: {e}")
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

    def _load_saved_credentials(self):
        nid, _ = load_credentials()
        if nid:
            self.naver_id_entry.insert(0, nid)
            self.cred_status.configure(text="자격증명 저장됨 (확인 필요)", text_color=T["text_tertiary"])

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

    def _on_start(self):
        url = self.url_entry.get().strip()
        if not url:
            self._log("상품 URL을 입력하세요.")
            return
        if not validate_smartstore_url(url):
            if not messagebox.askyesno(
                "URL 확인",
                "네이버 스마트스토어 URL이 아닌 것 같습니다.\n그래도 계속하시겠습니까?",
            ):
                return

        try:
            date_str = self.date_entry.get().strip()
            h = int(self.hour_entry.get().strip() or "0")
            m = int(self.min_entry.get().strip() or "0")
            s = int(self.sec_entry.get().strip() or "0")
            purchase_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=h, minute=m, second=s)
        except (ValueError, AttributeError):
            self._log("구매 일시 형식 오류 (YYYY-MM-DD)")
            return

        if purchase_dt <= datetime.now():
            self._log(f"구매 시간이 과거입니다: {purchase_dt}")
            return

        try:
            qty = int(self.qty_entry.get().strip() or "1")
        except ValueError:
            self._log("수량은 숫자여야 합니다.")
            return
        if qty < 1 or qty > 99:
            self._log("수량은 1~99 사이여야 합니다.")
            return

        options = {}
        opt_desc = []
        for i, entry in enumerate(self.option_entries, 1):
            val = entry.get().strip()
            options[f"option{i}"] = val if val else None
            if val:
                opt_desc.append(f"옵션{i}={val}")

        opt_text = ", ".join(opt_desc) if opt_desc else "없음"
        retry_text = ""
        if self.retry_var.get():
            ri = self.retry_interval_entry.get().strip()
            rm = self.retry_max_entry.get().strip()
            retry_text = f"\n재시도: {ri}초 간격, 최대 {rm}회"

        confirm_msg = (
            f"다음 설정으로 자동 구매를 시작합니다:\n\n"
            f"URL: {url[:50]}...\n"
            f"구매 시간: {purchase_dt.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"수량: {qty}개\n"
            f"옵션: {opt_text}"
            f"{retry_text}\n\n"
            f"실제 주문이 이루어집니다. 계속하시겠습니까?"
        )
        if not messagebox.askyesno("구매 확인", confirm_msg, icon="warning"):
            self._log("시작 취소됨")
            return

        self._total_wait = (purchase_dt - datetime.now()).total_seconds()

        try:
            retry_interval = float(self.retry_interval_entry.get().strip() or "1.0")
            retry_max = int(self.retry_max_entry.get().strip() or "60")
        except ValueError:
            retry_interval = 1.0
            retry_max = 60

        pre_nav = int(self.pre_nav_entry.get().strip() or "30")
        profile = self.profile_entry.get().strip()

        self.scheduler.configure(
            product_url=url,
            purchase_time=purchase_dt,
            options=options,
            quantity=qty,
            use_ntp=self.ntp_var.get(),
            chrome_profile=profile,
            pre_navigate_seconds=pre_nav,
            retry_enabled=self.retry_var.get(),
            retry_preset="custom",
            retry_interval=retry_interval,
            retry_max=retry_max,
        )

        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.status_label.configure(text="실행 중", fg_color=T["primary"])
        self.retry_label.configure(text="")

        self._log(f"스케줄 시작: {purchase_dt.strftime('%Y-%m-%d %H:%M:%S')} | 수량: {qty} | {opt_text}")
        self.scheduler.start()

    def _on_stop(self):
        self.scheduler.stop()
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.status_label.configure(text="중지됨", fg_color=T["danger"])
        self.countdown_label.configure(text="00:00:00.000", text_color=T["countdown_normal"])
        self.progress_bar.set(0)
        self.retry_label.configure(text="")

    def _on_complete(self):
        self.after(0, self._ui_complete)

    def _ui_complete(self):
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.status_label.configure(text="완료", fg_color=T["warning"])
        self.progress_bar.set(1)
        # 사운드 알림
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass

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
        if self.scheduler.is_running:
            if not messagebox.askyesno("종료 확인", "스케줄러가 실행 중입니다. 정말 종료하시겠습니까?"):
                return
            self.scheduler.stop()
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
        config = {
            "product_url": self.url_entry.get().strip(),
            "purchase_date": self.date_entry.get().strip(),
            "purchase_hour": self.hour_entry.get().strip(),
            "purchase_min": self.min_entry.get().strip(),
            "purchase_sec": self.sec_entry.get().strip(),
            "option1": self.option_entries[0].get().strip(),
            "option2": self.option_entries[1].get().strip(),
            "option3": self.option_entries[2].get().strip(),
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

        _set(self.url_entry, "product_url")
        _set(self.date_entry, "purchase_date")
        _set(self.hour_entry, "purchase_hour")
        _set(self.min_entry, "purchase_min")
        _set(self.sec_entry, "purchase_sec")
        _set(self.option_entries[0], "option1")
        _set(self.option_entries[1], "option2")
        _set(self.option_entries[2], "option3")
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
