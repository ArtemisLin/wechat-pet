@echo off
chcp 65001 >nul
cd /d "%~dp0pet"
echo.
echo   === WeChat Pet ===
echo.

if not exist ilink_state.json (
    echo   First launch - scan QR code to login...
    echo.
    py ilink.py login
    if errorlevel 1 (
        echo   Login failed, please retry
        pause
        exit /b
    )
    echo.
)

echo   Starting...
echo.
py ilink.py start
pause
