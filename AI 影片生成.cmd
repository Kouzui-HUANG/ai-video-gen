@echo off
chcp 65001 >nul
rem 「AI 影片生成」的 Windows 一鍵啟動：雙擊這個檔案，伺服器沒在跑就在背景啟動，準備好後打開瀏覽器。
rem 這裡只負責找到能執行 windows\launcher.py 的 Python 3.9 以上版本（專案的 .venv 優先），其他的事都在 launcher.py。
rem 前兩行只能有英文：chcp 65001 之後，cmd.exe 才會用 UTF-8 讀接下來的中文。
rem 自動更新可能在這個檔案執行到一半時改寫它，而 cmd.exe 是邊執行邊讀檔，
rem 所以執行 launcher.py 那一行的最後用 exit /b 結束，之後不會再讀到改過的內容。
rem 刻意不用標籤和 goto：換行被改成 LF 時，cmd.exe 找標籤可能會跳錯行。
setlocal EnableExtensions DisableDelayedExpansion
title AI 影片生成
if not exist "%~dp0windows\launcher.py" echo 找不到 windows\launcher.py。這個檔案要留在專案資料夾裡（和 video_ui.py 同一層），想放在桌面請改用右鍵的「傳送到 → 桌面（建立捷徑）」。 & pause & exit /b 1
set "PY_EXE="
set "PY_ARG="
set "PY_OK=import sys; sys.exit(sys.version_info < (3, 9))"
if exist "%~dp0.venv\Scripts\python.exe" "%~dp0.venv\Scripts\python.exe" -c "%PY_OK%" <nul >nul 2>&1 && set "PY_EXE=%~dp0.venv\Scripts\python.exe"
if not defined PY_EXE python -c "%PY_OK%" <nul >nul 2>&1 && set "PY_EXE=python"
if not defined PY_EXE py -3 -c "%PY_OK%" <nul >nul 2>&1 && set "PY_EXE=py" && set "PY_ARG=-3"
if not defined PY_EXE python3 -c "%PY_OK%" <nul >nul 2>&1 && set "PY_EXE=python3"
if defined PY_EXE "%PY_EXE%" %PY_ARG% "%~dp0windows\launcher.py" %* & exit /b

echo 找不到 Python 3.9 以上的版本。這個工具要用 Python 執行，請先安裝：
echo   1. 到 https://www.python.org/downloads/windows/ 下載並安裝 Python
echo   2. 裝好之後，再雙擊一次「AI 影片生成」
echo.
choice /c YN /n /m "要現在打開 Python 的下載頁嗎？[Y/N] "
if not errorlevel 2 start "" "https://www.python.org/downloads/windows/"
exit /b 1
