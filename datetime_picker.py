# -*- coding: utf-8 -*-
"""날짜/시간 피커 위젯 — CustomTkinter 기반"""

import calendar
from datetime import datetime, timedelta

import customtkinter as ctk


class CalendarPopup(ctk.CTkToplevel):
    """달력 팝업 — 날짜 선택"""

    def __init__(self, parent, on_select, current_date=None, **kwargs):
        super().__init__(parent, **kwargs)

        self.on_select = on_select
        self.title("날짜 선택")
        self.geometry("320x340")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        now = current_date or datetime.now()
        self.year = now.year
        self.month = now.month
        self.selected_day = now.day

        self.configure(fg_color="#FFFFFF")
        self._build()

    def _build(self):
        # 헤더: << < 2026년 3월 > >>
        header = ctk.CTkFrame(self, fg_color="#FFFFFF")
        header.pack(fill="x", padx=10, pady=(10, 5))

        ctk.CTkButton(
            header, text="<<", width=32, height=28,
            fg_color="#F8F9FD", hover_color="#EDF0F5", text_color="#303236",
            command=lambda: self._change_month(-12),
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            header, text="<", width=32, height=28,
            fg_color="#F8F9FD", hover_color="#EDF0F5", text_color="#303236",
            command=lambda: self._change_month(-1),
        ).pack(side="left", padx=2)

        self.month_label = ctk.CTkLabel(
            header, text="",
            font=ctk.CTkFont(family="Malgun Gothic", size=15, weight="bold"),
            text_color="#303236",
        )
        self.month_label.pack(side="left", expand=True)

        ctk.CTkButton(
            header, text=">", width=32, height=28,
            fg_color="#F8F9FD", hover_color="#EDF0F5", text_color="#303236",
            command=lambda: self._change_month(1),
        ).pack(side="right", padx=2)

        ctk.CTkButton(
            header, text=">>", width=32, height=28,
            fg_color="#F8F9FD", hover_color="#EDF0F5", text_color="#303236",
            command=lambda: self._change_month(12),
        ).pack(side="right", padx=2)

        # 요일 헤더
        days_header = ctk.CTkFrame(self, fg_color="#FFFFFF")
        days_header.pack(fill="x", padx=10, pady=(5, 0))
        for day_name in ["일", "월", "화", "수", "목", "금", "토"]:
            color = "#FF545C" if day_name == "일" else ("#1088ED" if day_name == "토" else "#767A83")
            ctk.CTkLabel(
                days_header, text=day_name, width=38,
                font=ctk.CTkFont(family="Malgun Gothic", size=12),
                text_color=color,
            ).pack(side="left", padx=1)

        # 날짜 그리드
        self.grid_frame = ctk.CTkFrame(self, fg_color="#FFFFFF")
        self.grid_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # 오늘 버튼
        ctk.CTkButton(
            self, text="오늘", height=30,
            fg_color="#03C75A", hover_color="#00942D", text_color="#FFFFFF",
            font=ctk.CTkFont(family="Malgun Gothic", size=13),
            command=self._select_today,
        ).pack(pady=(0, 10))

        self._render_month()

    def _render_month(self):
        for w in self.grid_frame.winfo_children():
            w.destroy()

        self.month_label.configure(text=f"{self.year}년 {self.month}월")

        cal = calendar.Calendar(firstweekday=6)  # 일요일 시작
        today = datetime.now()

        row = 0
        for day_tuple in cal.itermonthdays2(self.year, self.month):
            day, weekday = day_tuple
            col = (weekday + 1) % 7  # 일=0, 월=1, ..., 토=6

            if day == 0:
                ctk.CTkLabel(self.grid_frame, text="", width=38, height=32).grid(row=row, column=col)
            else:
                is_today = (day == today.day and self.month == today.month and self.year == today.year)
                is_selected = (day == self.selected_day)

                if is_selected:
                    fg = "#03C75A"
                    text_color = "#FFFFFF"
                elif is_today:
                    fg = "#EDF0F5"
                    text_color = "#03C75A"
                else:
                    fg = "#FFFFFF"
                    if col == 0:
                        text_color = "#FF545C"
                    elif col == 6:
                        text_color = "#1088ED"
                    else:
                        text_color = "#303236"

                btn = ctk.CTkButton(
                    self.grid_frame, text=str(day), width=38, height=32,
                    fg_color=fg, hover_color="#EDF0F5",
                    text_color=text_color,
                    font=ctk.CTkFont(family="Malgun Gothic", size=12),
                    corner_radius=6,
                    command=lambda d=day: self._select_day(d),
                )
                btn.grid(row=row, column=col, padx=1, pady=1)

            if col == 6:
                row += 1

    def _change_month(self, delta):
        if abs(delta) >= 12:
            self.year += delta // 12
        else:
            self.month += delta
            if self.month > 12:
                self.month = 1
                self.year += 1
            elif self.month < 1:
                self.month = 12
                self.year -= 1
        self.selected_day = 0
        self._render_month()

    def _select_day(self, day):
        self.selected_day = day
        date_str = f"{self.year}-{self.month:02d}-{day:02d}"
        self.on_select(date_str)
        self.destroy()

    def _select_today(self):
        now = datetime.now()
        date_str = f"{now.year}-{now.month:02d}-{now.day:02d}"
        self.on_select(date_str)
        self.destroy()


class TimeSpinbox(ctk.CTkFrame):
    """시:분:초 스핀박스 — 위/아래 버튼 + 직접 입력"""

    def __init__(self, parent, font_family="Malgun Gothic", **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)

        self._font = font_family
        self.entries = {}

        for i, (label, key, max_val) in enumerate([("시", "hour", 23), ("분", "min", 59), ("초", "sec", 59)]):
            unit_frame = ctk.CTkFrame(self, fg_color="transparent")
            unit_frame.pack(side="left", padx=(0 if i == 0 else 4, 0))

            # 위 버튼
            ctk.CTkButton(
                unit_frame, text="▲", width=44, height=18,
                fg_color="#F8F9FD", hover_color="#EDF0F5", text_color="#767A83",
                font=ctk.CTkFont(size=9), corner_radius=4,
                command=lambda k=key, m=max_val: self._increment(k, m, 1),
            ).pack()

            # 입력 필드
            entry = ctk.CTkEntry(
                unit_frame, width=44, height=32,
                font=ctk.CTkFont(family=font_family, size=14),
                justify="center",
                fg_color="#FFFFFF", border_color="#E9EBF0",
                text_color="#303236", corner_radius=6,
            )
            entry.pack(pady=1)
            entry.insert(0, "00")
            self.entries[key] = (entry, max_val)

            # 아래 버튼
            ctk.CTkButton(
                unit_frame, text="▼", width=44, height=18,
                fg_color="#F8F9FD", hover_color="#EDF0F5", text_color="#767A83",
                font=ctk.CTkFont(size=9), corner_radius=4,
                command=lambda k=key, m=max_val: self._increment(k, m, -1),
            ).pack()

            # 구분자
            if i < 2:
                ctk.CTkLabel(
                    self, text=":", text_color="#767A83",
                    font=ctk.CTkFont(size=16, weight="bold"),
                ).pack(side="left", padx=1)

    def _increment(self, key, max_val, delta):
        entry, _ = self.entries[key]
        try:
            val = int(entry.get() or "0")
        except ValueError:
            val = 0
        val = (val + delta) % (max_val + 1)
        entry.delete(0, "end")
        entry.insert(0, f"{val:02d}")

    def get_values(self) -> tuple[int, int, int]:
        """(시, 분, 초) 반환"""
        result = []
        for key in ["hour", "min", "sec"]:
            entry, _ = self.entries[key]
            try:
                result.append(int(entry.get() or "0"))
            except ValueError:
                result.append(0)
        return tuple(result)

    def set_values(self, hour: int = 0, minute: int = 0, second: int = 0):
        for key, val in [("hour", hour), ("min", minute), ("sec", second)]:
            entry, _ = self.entries[key]
            entry.delete(0, "end")
            entry.insert(0, f"{val:02d}")
