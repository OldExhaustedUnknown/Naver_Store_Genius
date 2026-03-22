@echo off
echo ========================================
echo  SmartStore Auto Buyer - Build
echo ========================================
echo.

echo [1/3] Installing dependencies...
pip install -r requirements.txt pyinstaller >nul 2>&1

echo [2/3] Building EXE...
pyinstaller build.spec --noconfirm --clean

echo [3/3] Creating desktop shortcut...
python create_shortcut.py

echo.
echo ========================================
echo  Build complete!
echo  EXE: dist\SmartStoreAutoBuyer.exe
echo ========================================
pause
