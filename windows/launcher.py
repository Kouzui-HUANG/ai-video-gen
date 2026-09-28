"""Windows 的一鍵啟動：雙擊專案資料夾裡的「AI 影片生成.cmd」時執行。

和 macOS App 的 launch.sh 做一樣的事：伺服器沒在跑就在背景啟動，準備好後打開瀏覽器。
- 跑伺服器的 Python：專案的 .venv 優先，其次是「AI 影片生成.cmd」找到、正在執行這個檔案的 Python；
  兩個都沒有 requests 時，問要不要用 pip 安裝（有 .venv 就裝進 .venv）。
- 伺服器用 python.exe 在背景執行、不開視窗（video_ui.py --no-browser --idle-exit 600），網頁關閉、
  也沒有進行中的任務 10 分鐘後自己結束。不用 pythonw.exe：沒有主控台的程式每次呼叫 git（自動更新）
  都會閃出一個黑色視窗。
- 輸出接在 outputs\\video_ui.log 後面；伺服器沒有啟動成功時，在這個視窗顯示記錄的最後幾行。

參數 --no-browser：只啟動伺服器，不打開瀏覽器。埠號看環境變數 VIDEO_UI_PORT（預設 8765）。
在 macOS／Linux 上也能執行（方便測試），不過那邊平常用 App 或直接執行 video_ui.py。
"""
import argparse
import http.client
import os
import socket
import subprocess
import sys
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:
    import fcntl

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = ROOT / "outputs"
LOG = OUTPUTS / "video_ui.log"
WINDOWS = os.name == "nt"
VENV_PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if WINDOWS else "bin/python")
PORT = os.environ.get("VIDEO_UI_PORT") or "8765"
URL = f"http://127.0.0.1:{PORT}/"
IDLE_EXIT = 600  # 和 launch.sh 一樣
WAIT = 60  # 最多等伺服器幾秒：有新版時要先下載、更新再重新啟動，Windows 上 git 和 Python 啟動都比較慢
CHECK = "import sys, requests; sys.exit(sys.version_info < (3, 9))"  # 能跑伺服器的 Python：3.9 以上、裝了 requests
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # 直接連本機，不走系統設定的 proxy


def running():
    """伺服器是不是已經在跑：和 launch.sh 一樣，看 /api/config 有沒有 model 欄位。"""
    try:
        # 先用很短的逾時試連：Windows 連到沒人在聽的埠，要重試一兩秒才會被拒絕
        socket.create_connection(("127.0.0.1", int(PORT)), timeout=0.5).close()
        with OPENER.open(URL + "api/config", timeout=3) as resp:
            return b'"model"' in resp.read()
    except (OSError, http.client.HTTPException):
        return False


def pause():
    """雙擊執行時，程式一結束視窗就關了：先讓使用者看完訊息。"""
    if sys.stdin and sys.stdin.isatty():
        try:
            input("\n按 Enter 關閉視窗…")
        except (EOFError, KeyboardInterrupt):
            pass


def fail(message):
    print(message)
    pause()
    sys.exit(1)


def ask(prompt):
    """問是或否；沒有人可以回答（例如輸入被導向）時當成否。"""
    if not (sys.stdin and sys.stdin.isatty()):
        return False
    while True:
        try:
            answer = input(prompt).strip().lower()
        except EOFError:
            return False
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False


def wait_turn():
    """同時雙擊好幾次時一個一個來：後面的等前面的把伺服器叫起來，再直接打開網頁，不會開出兩個伺服器。
    鎖檔一直開著，程式結束時自動解鎖；前一個卡住太久就不等了。"""
    OUTPUTS.mkdir(exist_ok=True)
    fd = os.open(OUTPUTS / "launcher.lock", os.O_RDWR | os.O_CREAT)
    deadline = time.monotonic() + WAIT + 15
    waiting = False
    while True:
        try:
            if WINDOWS:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError:
            if time.monotonic() > deadline:
                return
            if not waiting:
                print("另一個視窗正在啟動伺服器，等它完成…")
                waiting = True
            time.sleep(0.3)


def works(python):
    try:
        return subprocess.run([str(python), "-c", CHECK], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def find_python():
    """挑一個能跑伺服器的 Python；都缺 requests 時問要不要安裝。"""
    venv = [VENV_PYTHON] if VENV_PYTHON.exists() else []
    for python in dict.fromkeys([*venv, Path(sys.executable)]):
        if works(python):
            return python
    python = venv[0] if venv else Path(sys.executable)
    command = f'"{python}" -m pip install requests'
    print("找不到 requests 套件（伺服器用它連線到各家 API）。")
    if not ask(f"要現在安裝到 {python} 嗎？[Y/N] "):
        fail(f"沒有安裝。要自己安裝的話，在命令提示字元執行：\n  {command}")
    print("正在安裝 requests…")
    if subprocess.run([str(python), "-m", "pip", "install", "requests"]).returncode or not works(python):
        fail(f"安裝失敗，原因見上面的訊息。也可以在命令提示字元自己執行：\n  {command}")
    print("安裝完成，繼續啟動。")
    return python


def start_server(python):
    OUTPUTS.mkdir(exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as log:
        log.write(f"=== {time.strftime('%Y-%m-%d %H:%M:%S')} 由 Windows 啟動器啟動（{python}）===\n")
        log.flush()
        return subprocess.Popen(
            [str(python), "-u", "video_ui.py", "--port", PORT, "--no-browser", "--idle-exit", str(IDLE_EXIT)],
            cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            # 不開視窗，但有自己的（看不見的）主控台：自動更新呼叫 git 時不會閃出黑色視窗，
            # 關掉這個視窗或按 Ctrl+C 也不會影響伺服器。macOS／Linux 則是開新的 session
            creationflags=subprocess.CREATE_NO_WINDOW if WINDOWS else 0, start_new_session=True)


def wait_ready(proc):
    """等伺服器可以連線；伺服器先結束了（埠被佔用、程式錯誤等）或等太久就不等了。"""
    start = time.monotonic()
    while True:
        elapsed = time.monotonic() - start
        hint = "（可能正在檢查或下載新版本）" if elapsed >= 5 else ""
        print(f"\r正在啟動伺服器… {int(elapsed)} 秒{hint}", end="", flush=True)
        ready = running()
        if ready or proc.poll() is not None or elapsed > WAIT:
            print()
            return ready
        time.sleep(0.5)


def tail(lines=12):
    try:
        with open(LOG, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 16384))
            text = f.read().decode("utf-8", errors="replace")
    except OSError as e:
        return f"（讀不到記錄檔：{e}）"
    return "\n".join(text.splitlines()[-lines:])


def main():
    p = argparse.ArgumentParser(description="在背景啟動影片和圖片生成介面，準備好後打開瀏覽器（「AI 影片生成.cmd」用）")
    p.add_argument("--no-browser", action="store_true", help="只啟動伺服器，不打開瀏覽器")
    args = p.parse_args()
    if WINDOWS:  # 輸出被導向檔案時，Windows 用系統編碼（例如英文版的 cp1252），印中文會出錯
        for stream in (sys.stdout, sys.stderr):
            if stream and not stream.isatty():
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    if not (PORT.isascii() and PORT.isdigit() and 0 < int(PORT) < 65536):
        fail(f"環境變數 VIDEO_UI_PORT 要是埠號（例如 8765），現在是「{PORT}」。")

    wait_turn()
    if running():
        status = "伺服器已經在執行"
    else:
        proc = start_server(find_python())
        if not wait_ready(proc):
            if proc.poll() is None:
                fail(f"伺服器超過 {WAIT} 秒還沒準備好，可能還在下載新版本，請等一下再雙擊一次。"
                     f"最後幾行記錄（{LOG}）：\n{tail()}")
            fail(f"伺服器沒有啟動成功。最後幾行記錄（{LOG}）：\n{tail()}")
        status = "伺服器已就緒"
    if args.no_browser:
        print(f"{status}：{URL}")
    else:
        print(f"{status}，正在打開瀏覽器。")
        if not webbrowser.open(URL):
            fail(f"打不開瀏覽器，請自己用瀏覽器打開 {URL}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception:  # 程式本身出錯時也讓視窗留著，看得到原因
        traceback.print_exc()
        pause()
        sys.exit(1)
