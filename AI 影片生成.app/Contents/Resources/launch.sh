#!/bin/bash
# 「AI 影片生成」App 雙擊時執行：伺服器沒在跑就在背景啟動，準備好後打開瀏覽器。
# 網頁關掉 10 分鐘、也沒有進行中的任務時，伺服器會自己結束。記錄寫在 outputs/video_ui.log。
# 參數 $1：App 本身的路徑（由 AppleScript 傳入）

PROJECT_DEFAULT="/Users/kouzuimac/Documents/claude_code/ai-video-gen"
APP_PARENT="$(dirname "${1%/}")"
if [ -f "$APP_PARENT/video_ui.py" ]; then PROJECT="$APP_PARENT"; else PROJECT="$PROJECT_DEFAULT"; fi
if [ ! -f "$PROJECT/video_ui.py" ]; then
  echo "找不到 video_ui.py。請把這個 App 放在專案資料夾（和 video_ui.py 同一層）。" >&2
  echo "如果剛才拒絕了取用「文件」檔案夾，請到「系統設定 › 隱私權與安全性 › 檔案與檔案夾」開啟。" >&2
  exit 1
fi

PORT="${VIDEO_UI_PORT:-8765}"
URL="http://127.0.0.1:$PORT/"
LOG="$PROJECT/outputs/video_ui.log"
running() { curl -s -m 2 "${URL}api/config" 2>/dev/null | grep -q '"model"'; }

if ! running; then
  # 從 Finder 開啟時沒有終端機的 PATH，用登入 shell 找出裝好 requests 的 python3
  PY=""
  for cand in "$(/bin/zsh -lc 'command -v python3' 2>/dev/null | tail -n 1)" \
              /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
              /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if [ -n "$cand" ] && [ -x "$cand" ] && "$cand" -c "import requests" 2>/dev/null; then
      PY="$cand"
      break
    fi
  done
  if [ -z "$PY" ]; then
    echo "找不到裝有 requests 的 python3。請在終端機執行：pip3 install requests" >&2
    exit 1
  fi
  mkdir -p "$PROJECT/outputs"
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') 由 App 啟動（$PY）===" >> "$LOG"
  # 經過登入 shell 啟動，~/.zprofile 裡的 MIXROUTE_API_KEY 也會生效
  nohup /bin/zsh -lc 'cd "$1" && exec "$2" -u video_ui.py --port "$3" --no-browser --idle-exit 600' \
    _ "$PROJECT" "$PY" "$PORT" >> "$LOG" 2>&1 < /dev/null &
  SERVER_PID=$!
  for _ in $(seq 40); do
    running && break
    kill -0 "$SERVER_PID" 2>/dev/null || break  # 啟動失敗就不用再等
    sleep 0.25
  done
  if ! running; then
    echo "伺服器沒有啟動成功。最後幾行記錄（$LOG）：" >&2
    tail -n 12 "$LOG" >&2
    exit 1
  fi
fi
open "$URL"
