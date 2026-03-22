# -*- coding: utf-8 -*-
"""바탕화면 바로가기 생성 (C2 수정: PowerShell 인젝션 방지)"""

import os
import subprocess
from pathlib import Path


def _escape_ps(value: str) -> str:
    """PowerShell 문자열 이스케이프 (C2 수정)"""
    return value.replace("'", "''")


def create_desktop_shortcut():
    """바탕화면에 Naver Store Genius 바로가기 생성"""
    # .NET으로 정확한 바탕화면 경로 획득 (cp949/utf-8 모두 대응)
    try:
        result = subprocess.run(
            ["powershell", "-Command", "[Environment]::GetFolderPath('Desktop')"],
            capture_output=True,
        )
        desktop = result.stdout.decode("utf-8", errors="replace").strip()
        if not desktop or "\ufffd" in desktop:
            desktop = result.stdout.decode("cp949", errors="replace").strip()
    except Exception:
        desktop = ""
    if not desktop:
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")

    dist_dir = Path(__file__).parent / "dist"
    exe_path = dist_dir / "SmartStoreAutoBuyer.exe"

    if not exe_path.exists():
        print(f"EXE 파일 없음: {exe_path}")
        return False

    icon_path = Path(__file__).parent / "app_icon.ico"
    shortcut_path = os.path.join(desktop, "Naver Store Genius.lnk")

    # C2 수정: 경로 이스케이프
    ps_script = (
        f"$WshShell = New-Object -ComObject WScript.Shell; "
        f"$s = $WshShell.CreateShortcut('{_escape_ps(shortcut_path)}'); "
        f"$s.TargetPath = '{_escape_ps(str(exe_path))}'; "
        f"$s.WorkingDirectory = '{_escape_ps(str(dist_dir))}'; "
        f"$s.IconLocation = '{_escape_ps(str(icon_path))}'; "
        f"$s.Description = 'Naver Store Genius'; "
        f"$s.Save()"
    )
    result = subprocess.run(
        ["powershell", "-Command", ps_script],
        capture_output=True, encoding="utf-8",
    )
    if result.returncode == 0:
        print(f"바탕화면 바로가기 생성: {shortcut_path}")
        return True
    else:
        print(f"바로가기 생성 실패: {result.stderr}")
        return False


if __name__ == "__main__":
    create_desktop_shortcut()
