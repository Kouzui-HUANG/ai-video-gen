#!/usr/bin/env python3
"""影片和圖片生成的網頁介面：在本機開一個小伺服器，用瀏覽器放素材、送任務、看結果。

用法（需要 `pip install requests`）：
    python3 video_ui.py                  # 開 http://127.0.0.1:8765 並自動打開瀏覽器
    python3 video_ui.py --port 9000 --no-browser
    也可以直接雙擊專案資料夾裡的「AI 影片生成」App（macOS）或「AI 影片生成.cmd」（Windows），背景啟動、閒置後自動結束。

- 網頁右上角可切換 API：MixRoute（mixroute_video.py）或 GMI Cloud（gmi_video.py），模型用下拉選單選：兩邊都有
  Wan 3.0（wan3.0-video），GMI 另有 Seedance 2.0（seedance-2-0-260128）、Seedance 2.5（seedance-2-5-260628）
  和 MiniMax H3（MiniMax-H3）。
  各模型的參數與素材限制在 video_models.py，網頁依它調整左邊的表單；切換時素材、提示詞和共用的參數都會保留。
- 右上角切到「圖片」可以用 GMI 的 GPT Image 2.5（Sunburst、Flare）、GPT Image 2、Gemini 3 Pro Image 和
  Seedream 5.0 Pro（gmi_image.py）生成圖片：GPT Image 沒有參考圖時送 -generate（文字生圖），有參考圖時送 -edit
  （改圖、合成）；Gemini、Seedream 只有一個模型 ID，有參考圖就一起送。參數與價格在 image_models.py；
  提示詞和參考圖和影片共用。
  GPT Image 和 Gemini 是同步的：送出後要等圖片生成完 GMI 才回應，所以伺服器先建一筆任務，在背景等結果再下載；
  Seedream 是非同步的，送出後照影片的方式查到完成。Gemini、Seedream 一次只生成一張，張數 2 以上時伺服器把
  同一個請求送出多次，結果放在同一筆任務（見 _run_image_parts）。
- API key：優先用環境變數 MIXROUTE_API_KEY／GMI_API_KEY，沒有的話在網頁上輸入（只放在伺服器記憶體）。
- MixRoute：本機圖片在瀏覽器處理後以 base64 直接送出，不經第三方；本機影片、音訊、文件會上傳到
  Litterbox (litterbox.catbox.moe) 取得臨時公開網址，到期自動刪除，期間拿到連結的人都能下載。
- GMI：素材只收公開網址，本機圖片、影片、音訊在送出時上傳到 GMI 自己的儲存空間取得公開網址
  （拿到連結的人都能下載）；不支援文件和網頁素材。
- 完成的影片存成 <task_id>.mp4，圖片存成 <request_id>.png（一次多張時加 -1、-2…），放在輸出資料夾：預設是 outputs/，
  可以在選項改成別的資料夾（只影響之後的檔案，任務紀錄記著每個檔案存在哪裡）。
  任務紀錄在 outputs/tasks.json；加入過的本機素材副本在 outputs/inputs/（重用設定、臨時連結過期重傳時會用到）。
- 網頁右上角的齒輪是「選項」：主題（跟隨系統／亮色／暗色）、語言（目前只有繁體中文）、啟動時自動更新、
  任務完成時的通知與提示音、輸出資料夾，存在 outputs/settings.json。通知和提示音由網頁發出，網頁要開著（在背景也可以）。
- 自動更新（updater.py）：啟動時比對 GitHub 上 main 的最新 commit，有新版就用 git 快轉更新，再重新啟動自己載入新版。
  只支援用 git clone 下載的專案；本機有還沒 commit 的修改、還沒推上 GitHub 的 commit，或不在 main 分支時略過。
"""
import argparse
import base64
import hashlib
import json
import mimetypes
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
import time
import traceback
import uuid
import webbrowser
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests

import gmi_image
import gmi_video
import image_models
import updater
import video_models
import mixroute_video
from mixroute_video import BASE_URL, FAILED, check_http

ROOT = Path(__file__).resolve().parent
HTML_FILE = ROOT / "video_ui.html"
OUTPUTS = ROOT / "outputs"
INPUTS = OUTPUTS / "inputs"
TASKS_FILE = OUTPUTS / "tasks.json"
SETTINGS_FILE = OUTPUTS / "settings.json"

LITTERBOX_API = "https://litterbox.catbox.moe/resources/internals/api.php"
LITTERBOX_TTLS = {"1h": 3600, "12h": 12 * 3600, "24h": 24 * 3600, "72h": 72 * 3600}
REUPLOAD_MARGIN = 20 * 60  # 臨時連結剩不到 20 分鐘就重傳，避免任務排隊時連結過期
POLL_TIMEOUT = 2 * 3600
IMAGE_TIMEOUT = 15 * 60  # 圖片模型是同步的，送出後要等生成完才回應；max 品質、4K、一次多張時要好幾分鐘
IMAGE_PARALLEL = 4  # 一次只生成一張的模型要多張時，最多同時送出幾個請求（太多容易被限流）

IMAGE_MIME = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp", "bmp": "image/bmp"}
MAX_IMAGE_BYTES = 20 << 20
MAX_JSON_BYTES = 1 << 20
# kind: (允許的副檔名, 大小上限)。Litterbox 不收 .doc/.docx，這兩種只能改貼網址或轉成 PDF
UPLOAD_RULES = {
    "video": ({"mp4", "mov"}, 100 << 20),
    "audio": ({"wav", "mp3"}, 15 << 20),
    "file": ({"xlsx", "xls", "pptx", "ppt", "pdf", "txt", "key", "pages", "numbers", "md"}, 100 << 20),
}
# 網頁送來的素材類型（和 mixroute_video 的 media type 相同）；各模型支援哪些、最多幾個在 video_models.py
MEDIA_NAMES = {
    "first_frame": "首幀", "last_frame": "尾幀", "reference_image": "參考圖片",
    "reference_video": "參考影片", "reference_audio": "參考音訊", "file": "文件", "link": "網頁",
}

# 任務紀錄沒有 provider 欄位的是加入 GMI 之前建立的，都算 MixRoute；沒有 model 欄位的是加入模型切換之前的，都是 Wan 3.0
PROVIDERS = {
    "mixroute": {"label": "MixRoute", "env": "MIXROUTE_API_KEY"},
    "gmi": {"label": "GMI Cloud", "env": "GMI_API_KEY"},
}
DEFAULT_MODEL = "wan3.0-video"
SPECS = {(m["provider"], m["id"]): m for m in video_models.MODELS}
# 圖片模型用 image_models.py 的 id（例如 gpt-image-2.5-sunburst）選，送出時才依有沒有參考圖換成 generate／edit 的 ID。
# 任務紀錄有 kind: "image"，沒有 kind 的都是影片
IMAGE_SPECS = {m["id"]: m for m in image_models.MODELS}
# 選項（網頁右上角的齒輪）每一項可選的值，第一個是預設。存在伺服器這邊而不是瀏覽器：啟動時網頁還沒開，就要知道要不要檢查更新
SETTING_CHOICES = {
    "auto_update": (True, False),
    "theme": ("system", "light", "dark"),
    "language": ("zh-Hant",),  # 語言切換先留位置，之後再加 en
    "notify": (False, True),  # 任務完成、失敗時跳系統通知（瀏覽器另外要允許）
    "sound": (False, True),  # 任務完成、失敗時播放提示音
}
DEFAULT_SETTINGS = {name: choices[0] for name, choices in SETTING_CHOICES.items()}
# 輸出資料夾：生成的影片、圖片存在哪裡。None 是專案的 outputs/，不然是使用者選的完整路徑（能不能用，存的時候和下載時才檢查）
DEFAULT_SETTINGS["outputs_dir"] = None
UPDATED_ENV = "VIDEO_UI_UPDATED"  # 更新後重新啟動時，用這個環境變數把更新結果交給新的程序

# 選項「輸出資料夾」按「變更…」時跳出的系統選擇資料夾視窗（見 picker_command）
PICK_PROMPT = "選擇輸出資料夾：生成的影片和圖片會存到這裡"
# macOS：用 JXA 直接開 NSOpenPanel。AppleScript 的 choose folder 從背景程序跳出來會被瀏覽器擋在後面，這裡先把自己設成前景
MAC_PICKER = """ObjC.import('AppKit');
function run(argv) {
  var app = $.NSApplication.sharedApplication;
  app.setActivationPolicy($.NSApplicationActivationPolicyAccessory);
  app.activateIgnoringOtherApps(true);
  var panel = $.NSOpenPanel.openPanel;
  panel.canChooseFiles = false;
  panel.canChooseDirectories = true;
  panel.canCreateDirectories = true;
  panel.message = argv[0];
  panel.prompt = argv[1];
  panel.directoryURL = $.NSURL.fileURLWithPathIsDirectory(argv[2], true);
  panel.level = $.NSModalPanelWindowLevel;
  return panel.runModal == $.NSModalResponseOK ? ObjC.unwrap(panel.URL.path) : '';
}"""
# Windows：PowerShell 的 FolderBrowserDialog。擁有者設成最上層視窗，才不會被瀏覽器擋住；
# 提示文字和一開始的資料夾用環境變數傳，路徑轉成 base64 輸出，中文不受主控台編碼影響
WIN_PICKER = """Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::EnableVisualStyles()
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = $env:VIDEO_UI_PICK_PROMPT
$dialog.ShowNewFolderButton = $true
$dialog.SelectedPath = $env:VIDEO_UI_PICK_START
if ($dialog.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) {
  [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($dialog.SelectedPath))
}
$owner.Dispose()
"""

store = None  # TaskStore，main() 建立
_keys = {name: {"value": os.environ.get(p["env"]) or None} for name, p in PROVIDERS.items()}
for _k in _keys.values():
    _k["source"] = "env" if _k["value"] else None
# 「API/模型」→ 價格（美元）：影片是解析度 → 每秒，圖片是品質 → 1024×1024 每張
_prices = {f"gmi/{model}": dict(p) for model, p in gmi_video.PRICES.items()}
_prices.update({f"gmi/{m['id']}": dict(m["prices"]) for m in image_models.MODELS})
_pollers = {}
_pollers_lock = threading.Lock()
_upload_cache = {}  # (本機檔名, ttl) -> (url, expires_at)
_gmi_uploads = {}  # 本機檔名 -> GMI 公開網址（GMI 文件說是穩定網址，伺服器開著就沿用）
_upload_lock = threading.Lock()
_last_request = time.monotonic()  # 給 --idle-exit 判斷網頁是否還開著
_settings = dict(DEFAULT_SETTINGS)  # main() 從 outputs/settings.json 讀進來
_settings_lock = threading.Lock()
_version = None  # 正在執行的版本（updater.current_version()），main() 設定
_update = None  # 最近一次檢查更新的結果，給選項頁顯示；關掉自動更新又還沒手動檢查時是 None
_update_lock = threading.Lock()
_restart_status = None  # 選項頁按了「立即更新並重新啟動」：伺服器停下後帶著這個結果重新啟動
_picker = None  # 正開著的選擇資料夾視窗（subprocess.Popen），一次只開一個
_picker_lock = threading.Lock()


class TaskStore:
    """任務紀錄，存在 outputs/tasks.json；每次變動都整份重寫（筆數不多）。"""

    def __init__(self, path):
        self.path = path
        self.lock = threading.RLock()
        self.tasks = {}
        self.closed = False
        if path.exists():
            try:
                for t in json.loads(path.read_text("utf-8")):
                    self.tasks[t["task_id"]] = t
            except (OSError, ValueError, KeyError, TypeError) as e:
                backup = path.with_name(f"{path.name}.bad-{int(time.time())}")
                os.replace(path, backup)
                print(f"讀不懂 {path.name}（{e}），已改名為 {backup.name}，從空的列表開始")

    def _save(self):
        if self.closed:
            return
        tasks = sorted(self.tasks.values(), key=lambda t: t["created_at"])
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(tasks, ensure_ascii=False, indent=1), "utf-8")
        os.replace(tmp, self.path)

    def add(self, task):
        with self.lock:
            task["updated_at"] = time.time()
            self.tasks[task["task_id"]] = task
            self._save()
            return dict(task)

    def update(self, task_id, **fields):
        with self.lock:
            task = self.tasks.get(task_id)
            if task is None or self.closed:  # 已從列表移除，或已經交給重新啟動的新程序
                return None
            task.update(fields, updated_at=time.time())
            self._save()
            return dict(task)

    def mutate(self, task_id, fn):
        """fn(目前的紀錄) 算出要更新的欄位再寫回，整段在鎖裡：好幾個執行緒同時改同一筆任務（多張圖片任務的每一張）時用。"""
        with self.lock:
            task = self.tasks.get(task_id)
            if task is None or self.closed:
                return None
            task.update(fn(dict(task)), updated_at=time.time())
            self._save()
            return dict(task)

    def close(self):
        """之後不再改紀錄、不再寫檔，查詢中的任務下次更新時就會停下（update 回傳 None）。
        Windows 重新啟動時舊程序要等新程序結束，執行緒還在跑，不擋的話兩邊會互相覆蓋 tasks.json。"""
        with self.lock:
            self.closed = True

    def get(self, task_id):
        with self.lock:
            task = self.tasks.get(task_id)
            return dict(task) if task else None

    def remove(self, task_id):
        with self.lock:
            if self.tasks.pop(task_id, None) is not None:
                self._save()

    def all(self):
        with self.lock:
            return sorted((dict(t) for t in self.tasks.values()), key=lambda t: t["created_at"], reverse=True)


def api_session(key):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {key}"
    return s


def error_message(body):
    """MixRoute 回 {"error": {"message": …}}；GMI 回 {"error": "…"} 或 {"message": "…"}。"""
    err = body.get("error")
    return (err.get("message") if isinstance(err, dict) else err) or body.get("message")


def error_text(resp):
    try:
        msg = error_message(resp.json())
    except (ValueError, AttributeError):
        msg = None
    return str(msg) if msg else resp.text[:300]


def friendly_error(e):
    """把 check_http 的「HTTP 400: {json}」整理成「HTTP 400：訊息」。"""
    text = str(e)
    m = re.match(r"HTTP (\d+): (.*)", text, re.S)
    if m:
        if m.group(2).lstrip().startswith("<"):
            return f"HTTP {m.group(1)}：伺服器回傳錯誤頁，請稍後再試"
        try:
            msg = error_message(json.loads(m.group(2)))
            if msg:
                return f"HTTP {m.group(1)}：{msg}"
        except (ValueError, AttributeError):
            pass
    return text


def provider_of(name):
    name = name or "mixroute"
    if not isinstance(name, str) or name not in PROVIDERS:
        raise ValueError(f"不支援的 API：{name}")
    return name


def spec_of(provider, model):
    """這個 API 的這個模型在 video_models.py 裡的設定。"""
    provider = provider_of(provider)
    spec = SPECS.get((provider, model or DEFAULT_MODEL)) if isinstance(model, (str, type(None))) else None
    if not spec:
        raise ValueError(f"{PROVIDERS[provider]['label']} 沒有 {model} 模型")
    return spec


def check_mixroute_key(key):
    """用免費的 /v1/models 檢查 key，回傳提醒文字（沒有就是空字串）。"""
    try:
        resp = requests.get(f"{BASE_URL}/models", headers={"Authorization": f"Bearer {key}"}, timeout=20)
    except requests.RequestException as e:
        return f"暫時無法向 MixRoute 驗證 key，先照用：{e}"
    if resp.status_code in (401, 403):
        raise ValueError(f"API key 無效：{error_text(resp)}")
    if not resp.ok:
        return f"驗證 key 時 HTTP {resp.status_code}，先照用"
    try:
        ids = {m.get("id") for m in resp.json().get("data", [])}
    except (ValueError, AttributeError):
        ids = None
    if ids is not None and mixroute_video.MODEL not in ids:
        return f"這把 key 的模型列表裡沒有 {mixroute_video.MODEL}，送出可能會失敗"
    return ""


def check_gmi_key(key):
    """用免費的模型列表 API 檢查 key，順便從各模型的說明更新價格。"""
    headers = {"Authorization": f"Bearer {key}"}
    try:
        resp = requests.get(f"{gmi_video.BASE_URL}/models", headers=headers, timeout=20)
    except requests.RequestException as e:
        return f"暫時無法向 GMI 驗證 key，先照用：{e}"
    if resp.status_code in (401, 403):
        raise ValueError(f"API key 無效：{error_text(resp)}")
    if not resp.ok:
        return f"驗證 key 時 HTTP {resp.status_code}，先照用"
    try:
        ids = set(resp.json().get("model_ids") or [])
    except (ValueError, AttributeError):
        ids = set()
    models = [m for m in video_models.MODELS if m["provider"] == "gmi"]
    # 「API/模型」→ (查哪個模型的說明, 怎麼讀價格)；圖片模型的 generate 和 edit 價格相同，查 generate 就好
    lookups = {f"gmi/{m['id']}": (m["id"], gmi_video.parse_prices) for m in models}
    image_parsers = {"sizes": gmi_image.parse_size_prices, "tiers": gmi_image.parse_tier_prices,
                     "flat": gmi_image.parse_flat_price}
    lookups.update({f"gmi/{m['id']}": (m["generate"], image_parsers.get(m["price_rule"], gmi_image.parse_prices))
                    for m in image_models.MODELS})

    def update_price(item):
        price_key, (model_id, parse) = item
        try:
            info = requests.get(f"{gmi_video.BASE_URL}/models/{model_id}", headers=headers, timeout=20)
            if info.ok:
                _prices.setdefault(price_key, {}).update(parse(info.json()))
        except (requests.RequestException, ValueError, AttributeError):
            pass  # 價格沿用公告價

    with ThreadPoolExecutor(max_workers=8) as pool:  # 一個一個查太慢，儲存 key 時要等
        list(pool.map(update_price, lookups.items()))
    wanted = [(m["label"], [m["id"]]) for m in models] + [(m["label"], [m["generate"], m["edit"]]) for m in image_models.MODELS]
    missing = [label for label, model_ids in wanted if ids and any(i not in ids for i in model_ids)]
    return f"這把 key 的模型列表裡沒有 {'、'.join(missing)}，選這些模型送出可能會失敗" if missing else ""


def check_env_gmi_key():
    try:
        warning = check_gmi_key(_keys["gmi"]["value"])
    except ValueError as e:
        warning = str(e)
    if warning:
        print(f"GMI_API_KEY：{warning}", flush=True)


def set_key(provider, key):
    warning = check_gmi_key(key) if provider == "gmi" else check_mixroute_key(key)
    _keys[provider].update(value=key, source="session")
    resume_pending(provider)
    return warning


def safe_name(task_id):
    return re.sub(r"[^A-Za-z0-9._-]", "_", task_id)


def input_path(name):
    if not re.fullmatch(r"[0-9a-f]{20}\.[a-z0-9]{1,8}", str(name)):
        raise ValueError(f"素材檔名不正確：{name}")
    return INPUTS / name


def save_input(data, ext):
    """以內容雜湊命名存到 outputs/inputs/，同一個檔案只存一份。"""
    name = f"{hashlib.sha256(data).hexdigest()[:20]}.{ext}"
    path = INPUTS / name
    if not path.exists():
        INPUTS.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
    return name


def sniff_image(data):
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:2] == b"BM":
        return "bmp"
    return None


def litterbox_upload(name, ttl, fresh=False):
    """把 outputs/inputs/<name> 傳到 Litterbox，回傳 (url, expires_at)；還夠新的連結直接沿用。"""
    now = time.time()
    with _upload_lock:
        cached = _upload_cache.get((name, ttl))
    if cached and not fresh and cached[1] - now > REUPLOAD_MARGIN:
        return cached
    path = input_path(name)
    with open(path, "rb") as f:
        resp = requests.post(
            LITTERBOX_API,
            data={"reqtype": "fileupload", "time": ttl},
            files={"fileToUpload": (path.name, f)},
            timeout=900,
        )
    if not resp.ok:
        # 錯誤時常回整頁 HTML（前面有 BunkerWeb 防護），只留狀態碼
        detail = "" if "<html" in resp.text[:500].lower() else f"：{resp.text.strip()[:200]}"
        raise RuntimeError(f"Litterbox 上傳失敗（HTTP {resp.status_code}{detail}），請稍後再試，或改貼其他公開網址")
    url = resp.text.strip()
    if not re.fullmatch(r"https://\S+", url):
        raise RuntimeError(f"Litterbox 上傳失敗：{url[:300]}")
    result = (url, now + LITTERBOX_TTLS[ttl])
    with _upload_lock:
        _upload_cache[(name, ttl)] = result
    return result


def gmi_upload(session, name):
    """把 outputs/inputs/<name> 傳到 GMI，回傳公開網址；同一個檔案只傳一次。"""
    with _upload_lock:
        url = _gmi_uploads.get(name)
    if url:
        return url
    url = gmi_video.upload(session, input_path(name))
    with _upload_lock:
        _gmi_uploads[name] = url
    return url


def clean_parameters(p, spec, frames=False, text_only=False):
    """依模型的設定檢查網頁送來的參數；frames 為真表示這次有首尾幀，text_only 為真表示沒有任何素材。"""
    label = spec["label"]
    if p.get("resolution") not in spec["resolutions"]:
        raise ValueError(f"{label} 的解析度只能是 {'、'.join(spec['resolutions'])}")
    ratio = p.get("ratio")
    if frames and spec["frame_ratio"] == "force":
        ratio = "adaptive"  # Seedance 的首尾幀模式一定要自適應，送別的比例要到生成時才報錯
    if ratio not in spec["ratios"]:
        raise ValueError(f"{label} 不支援 {ratio} 比例")
    if text_only and ratio == "adaptive" and not spec["text_adaptive"]:
        raise ValueError(f"{label} 純文字生影片不能用自適應比例，請指定比例")
    try:
        duration = int(p.get("duration"))
    except (TypeError, ValueError):
        raise ValueError("時長必須是整數") from None
    rule = spec["duration"]
    if not ((duration == -1 and rule["auto"]) or rule["min"] <= duration <= rule["max"]):
        raise ValueError(f"{label} 的時長必須是 {rule['min']}-{rule['max']} 秒" + ("或 -1（自動）" if rule["auto"] else ""))
    out = {"resolution": p["resolution"], "ratio": ratio, "duration": duration}
    out["audio"] = spec["audio"] == "always" or bool(p.get("audio"))
    for flag in spec["options"]:
        out[flag] = bool(p.get(flag))
    seed = p.get("seed")
    if seed not in (None, "") and spec["seed"]:  # 不能指定 seed 的模型（MiniMax H3）不送
        try:
            seed = int(seed)
        except (TypeError, ValueError):
            raise ValueError("Seed 必須是整數") from None
        rule = spec["seed"]
        if not ((seed == -1 and rule["random"]) or rule["min"] <= seed <= rule["max"]):
            raise ValueError(f"{label} 的 Seed 必須是 {'-1 或 ' if rule['random'] else ''}{rule['min']}-{rule['max']}")
        out["seed"] = seed
    return out


def check_media_rules(types, spec):
    label = spec["label"]
    counts = Counter(types)
    for typ, n in counts.items():
        limit = spec["media"].get(typ, 0)
        if not limit:
            raise ValueError(f"{label} 不支援{MEDIA_NAMES[typ]}素材")
        if n > limit:
            raise ValueError(f"{label} 的{MEDIA_NAMES[typ]}最多 {limit} 個")
    if len(types) > spec["media_total"]:
        raise ValueError(f"{label} 的素材總數最多 {spec['media_total']} 個")
    frames = counts["first_frame"] + counts["last_frame"]
    if counts["last_frame"] and not counts["first_frame"]:
        raise ValueError("用尾幀時必須也有首幀")
    if frames and len(types) > frames:
        raise ValueError("首尾幀不能和參考素材、文件或網頁一起用")
    if counts["file"] and counts["link"]:
        raise ValueError("文件和網頁只能擇一")
    if counts["reference_audio"] and not spec["audio_alone"] and not (counts["reference_image"] or counts["reference_video"]):
        raise ValueError(f"{label} 不能只用參考音訊，要搭配至少一張參考圖片或一段參考影片")


def resolve_media(items, spec, session=None, dry_run=False):
    """把網頁送來的素材轉成 API 的 media 陣列，回傳 (media, 給任務紀錄用的摘要)。

    MixRoute：本機圖片轉 base64，其他本機檔案用 Litterbox 臨時網址。
    GMI：本機檔案都傳到 GMI 的儲存空間，session 要帶 GMI 的 key。
    dry_run：預覽用，不上傳也不讀檔內容，還沒有網址的本機檔案換成說明文字。
    """
    gmi = spec["provider"] == "gmi"
    types = [item.get("type") for item in items]
    for typ in types:
        if typ not in MEDIA_NAMES:
            raise ValueError(f"不支援的素材類型：{typ}")
    check_media_rules(types, spec)  # 先檢查，不合規則就不用白傳檔案
    media, summaries = [], []
    for item, typ in zip(items, types):
        summary = {k: item[k] for k in ("id", "name", "duration", "width", "height", "bytes", "notes") if k in item}
        summary["type"] = typ
        name = item.get("name") or ""
        if item.get("ref"):  # 本機圖片
            path = input_path(item["ref"])
            ext = path.suffix[1:]
            mime = IMAGE_MIME.get(ext)
            if not mime or not path.exists():
                raise ValueError(f"找不到本機圖片「{name}」，請重新加入")
            if ext not in spec["image"]["formats"]:
                formats = "／".join("JPEG" if f == "jpg" else f.upper() for f in spec["image"]["formats"])
                raise ValueError(f"{spec['label']} 只接受 {formats}：請移除「{name}」後重新加入（會自動轉檔）")
            if dry_run:
                url = (_gmi_uploads.get(item["ref"]) or f"（本機圖片 {name}，送出時上傳到 GMI）") if gmi \
                    else f"data:{mime};base64,…（本機圖片 {name}）"
            elif gmi:
                url = summary["gmi_url"] = gmi_upload(session, item["ref"])
            else:
                url = f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"
            summary["ref"] = item["ref"]
        elif item.get("local"):  # 本機影片、音訊、文件
            if not input_path(item["local"]).exists():
                raise ValueError(f"找不到本機檔案「{name}」，請重新加入")
            if gmi:
                url = (_gmi_uploads.get(item["local"]) or f"（本機檔案 {name}，送出時上傳到 GMI）") if dry_run \
                    else gmi_upload(session, item["local"])
                summary.update(local=item["local"], gmi_url=url)
            else:
                ttl = item.get("ttl") if item.get("ttl") in LITTERBOX_TTLS else "1h"
                url, expires_at = item.get("url"), float(item.get("expires_at") or 0)
                if not url or expires_at - time.time() < REUPLOAD_MARGIN:
                    if dry_run:
                        url = f"（本機檔案 {name}，送出時上傳到 Litterbox）"
                    else:
                        url, expires_at = litterbox_upload(item["local"], ttl, fresh=True)
                summary.update(local=item["local"], url=url, expires_at=expires_at, ttl=ttl)
        else:
            url = str(item.get("url") or "").strip()
            if dry_run and not url:
                url = f"（{name or '素材'} 處理中）"
            elif urlparse(url).scheme not in ("http", "https"):
                raise ValueError(f"素材網址必須是 http 或 https：{url[:100]}")
            summary["url"] = url
        media.append({"type": typ, "url": url})
        summaries.append(summary)
    return media, summaries


def prepare_request(body, session=None, dry_run=False):
    """檢查網頁送來的內容並準備素材，回傳 (spec, prompt, negative, parameters, media, summaries)。"""
    spec = spec_of(body.get("provider"), body.get("model"))
    prompt = str(body.get("prompt") or "").strip()
    negative = str(body.get("negative_prompt") or "").strip() if spec["negative_max"] else ""
    items = body.get("media") or []
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise ValueError("素材格式不正確")
    if not prompt and not items:
        raise ValueError("請輸入提示詞或加入素材")
    if spec["prompt_required"] and not prompt:
        raise ValueError(f"{spec['label']} 需要提示詞")
    frames = any(item.get("type") in ("first_frame", "last_frame") for item in items)
    parameters = clean_parameters(body.get("parameters") or {}, spec, frames, text_only=not items)
    media, summaries = resolve_media(items, spec, session, dry_run)
    return spec, prompt, negative, parameters, media, summaries


def request_json(spec, prompt, negative, parameters, media):
    """實際送給 API 的 JSON（預覽用；送出時由各 API 模組自己組）。"""
    if spec["provider"] == "gmi":
        return {"model": spec["id"], "payload": gmi_video.build_payload(spec["id"], prompt, parameters, media, negative)}
    return mixroute_video.build_payload(prompt, parameters, media)


def explain_create_error(e, label, spec, media):
    """建立請求時對方回 5xx 的說明。GMI 會把上游（BytePlus、DashScope）的拒絕包成 500「Backend error (4xx)」。"""
    text, msg = str(e), friendly_error(e)
    # GMI 建立請求時會預扣費用：餘額不足、或參數組合沒有訂價（例如 Seedance 2.5 的 1080p、時長 -1）都回 500
    if re.search(r"billing|pre-charge|find price", text, re.I):
        return f"{label} 預扣費用失敗：可能是帳戶餘額不足，或 {label} 沒有這個參數組合的價格（{msg}）"
    faces = ""
    if not spec["real_faces"] and any(m["type"] in ("first_frame", "last_frame", "reference_image", "reference_video") for m in media):
        faces = f"如果素材裡有擬真的人臉（真人照片或 AI 生成的都算），{spec['label']} 會拒絕，請換成插畫風格或沒有人臉的素材。"
    if re.search(r"Backend error \(4(00|03|22)\)", text):
        return (f"{label} 轉給模型供應商時被拒絕（{msg}）：多半是素材或參數不合 {spec['label']} 的要求，"
                f"例如素材網址打不開，或尺寸、長寬比、長度不合。{faces}請求沒有建立，不收費。")
    if faces and re.search(r"temporary backend error|request was rejected", text, re.I):
        return f"{label} 拒絕了這個請求（{msg}）。{faces}素材沒有人臉的話，多半是 {label} 暫時的問題，請稍後再試。"
    # 其他 5xx 是對方伺服器的問題（例如 GMI 轉給上游 DashScope 時被拒，回 Backend error (401)），
    # 講清楚免得以為是自己的 key 或參數錯了
    return f"{label} 伺服器端錯誤，不是你的 key 或設定的問題，請稍後再試（{msg}）"


def create_task(body):
    provider = provider_of(body.get("provider"))
    label = PROVIDERS[provider]["label"]
    key = _keys[provider]["value"]
    if not key:
        raise ValueError(f"請先設定 {label} 的 API key")
    with api_session(key) as s:
        spec, prompt, negative, parameters, media, summaries = prepare_request(body, s)
        try:
            if provider == "gmi":
                task_id = gmi_video.create_task(s, prompt, parameters, media, negative, model=spec["id"])
            else:
                task_id = mixroute_video.create_task(s, prompt, parameters, media)
        except requests.Timeout:
            # 每次 POST 都會建立新任務，逾時不自動重送
            raise RuntimeError(f"送出逾時：任務可能已經建立，請先到 {label} 後台確認再決定要不要重送") from None
        except RuntimeError as e:
            if re.match(r"HTTP 5\d\d: ", str(e)):
                raise RuntimeError(explain_create_error(e, label, spec, media)) from None
            raise
    task = {
        "task_id": task_id,
        "provider": provider,
        "model": spec["id"],
        "created_at": time.time(),
        "mode": body.get("mode") or "",
        "prompt": prompt,
        "parameters": parameters,
        "media": summaries,
        "status": "QUEUED",
        "progress": "",
    }
    if negative:
        task["negative_prompt"] = negative
    record = store.add(task)
    start_poller(task_id)
    return record


# ---------- 圖片（GPT Image、Gemini） ----------
IMAGE_PARAM_KEYS = ("size", "quality", "n", "output_format", "output_compression", "background", "moderation",
                    "aspect_ratio", "image_size", "image_output_format", "watermark")


def image_spec_of(model):
    spec = IMAGE_SPECS.get(model) if isinstance(model, str) else None
    if not spec:
        raise ValueError(f"沒有 {model} 這個圖片模型")
    return spec


def image_family(model_id):
    """GMI 的模型 ID（…-generate／…-edit）屬於 image_models.py 的哪個模型。"""
    return next((m for m in image_models.MODELS if model_id in (m["generate"], m["edit"])), None)


def size_problem(w, h, rule):
    """輸出尺寸不合規則時回傳原因（網頁的 sizeProblem 是同一套）。"""
    if not w or not h:
        return "寬高不能是 0"
    k = rule["multiple"]
    if w % k or h % k:
        return f"寬高都必須是 {k} 的倍數"
    if max(w, h) > rule["max_side"]:
        return f"每邊最多 {rule['max_side']} px"
    if max(w, h) > min(w, h) * rule["max_ratio"]:
        return f"長寬比最多 {rule['max_ratio']}:1"
    if not rule["min_pixels"] <= w * h <= rule["max_pixels"]:
        return f"總像素要在 {rule['min_pixels']:,}–{rule['max_pixels']:,} 之間"
    return ""


def clean_image_parameters(p, spec, endpoint):
    """依圖片模型的設定檢查網頁送來的參數，回傳要放進 payload 的參數。endpoint 是 generate 或 edit：
    模型的這個端點不收的參數（extra_params 沒列的）直接不送，網頁上已經說明這次用什麼。"""
    label, extra = spec["label"], spec["extra_params"][endpoint]
    if spec["sizing"] == "ratio":  # Gemini：只送比例和解析度
        if p.get("aspect_ratio") not in spec["ratios"]:
            raise ValueError(f"{label} 的比例只能是 {'、'.join(spec['ratios'])}")
        if p.get("image_size") not in spec["tiers"]:
            raise ValueError(f"{label} 的解析度只能是 {'、'.join(spec['tiers'])}")
        out = {"aspect_ratio": p["aspect_ratio"], "image_size": p["image_size"]}
    else:
        m = re.fullmatch(r"(\d{1,5})x(\d{1,5})", str(p.get("size") or ""))
        if not m:
            raise ValueError("輸出尺寸的格式要像 1024x1024")
        w, h = int(m.group(1)), int(m.group(2))
        problem = size_problem(w, h, spec["size"])
        if problem:
            raise ValueError(f"{label} 的輸出尺寸 {w}×{h} 不行：{problem}")
        out = {"size": f"{w}x{h}"}
    if spec["qualities"]:  # Gemini、Seedream 沒有品質
        quality = p.get("quality")
        if quality not in spec["qualities"]:  # 不收 auto：GMI 會按 max 計價
            raise ValueError(f"{label} 的品質只能是 {'、'.join(spec['qualities'])}")
        out["quality"] = quality
    if spec["n_param"]:  # 一次只生成一張的模型（Gemini、Seedream）沒有 n，張數在 prepare_image_request 處理
        try:
            n = int(p.get("n", 1))
        except (TypeError, ValueError):
            raise ValueError("張數必須是整數") from None
        rule = spec["n"]
        if not rule["min"] <= n <= rule["max"]:
            raise ValueError(f"{label} 一次可以生成 {rule['min']}-{rule['max']} 張")
        out[spec["n_param"]] = n
    fmt = "png"  # 不收 output_format 的端點輸出 PNG
    if "output_format" in extra:
        name = spec["format_param"]  # Gemini 叫 image_output_format
        fmt = p.get(name) or spec["defaults"]["output_format"]
        if fmt not in spec["formats"]:
            raise ValueError(f"{label} 的輸出格式只能是 {'、'.join(spec['formats'])}")
        out[name] = fmt
    if "background" in extra:
        background = p.get("background") or "auto"
        if background not in spec["backgrounds"]:
            raise ValueError(f"{label} 不支援 {background} 背景")
        if background == "transparent" and fmt not in spec["transparent_formats"]:
            names = {"png": "PNG", "jpeg": "JPEG", "webp": "WebP"}
            raise ValueError(f"透明背景只能輸出 {'／'.join(names.get(f, f) for f in spec['transparent_formats'])}")
        out["background"] = background
    if "moderation" in extra:
        moderation = p.get("moderation") or "auto"
        if moderation not in spec["moderation"]:
            raise ValueError(f"內容審核只能是 {'、'.join(spec['moderation'])}")
        out["moderation"] = moderation
    if "output_compression" in extra and fmt in ("jpeg", "webp"):  # 壓縮只對 JPEG、WebP 有效
        try:
            compression = int(p.get("output_compression", spec["defaults"]["output_compression"]))
        except (TypeError, ValueError):
            raise ValueError("壓縮品質必須是整數") from None
        if not 0 <= compression <= 100:
            raise ValueError("壓縮品質必須是 0-100")
        out["output_compression"] = compression
    if "watermark" in extra:  # Seedream：右下角的「AI generated」字樣
        out["watermark"] = bool(p.get("watermark"))
    return out


def prepare_image_request(body, session=None, dry_run=False):
    """檢查網頁送來的圖片請求並準備參考圖，回傳 (spec, GMI 模型 ID, prompt, parameters, payload, summaries, count)。

    有參考圖用 edit，沒有用 generate；參考圖的處理和 GMI 的影片模型一樣（本機檔案上傳到 GMI 的儲存空間）。
    count 是同一個請求要送出幾次：一次只生成一張的模型（n_param 是 None）靠它生成多張，其他模型一律 1。
    """
    spec = image_spec_of(body.get("model"))
    prompt = str(body.get("prompt") or "").strip()
    if not prompt:
        raise ValueError(f"{spec['label']} 需要提示詞")
    items = body.get("media") or []
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise ValueError("素材格式不正確")
    count = 1
    if spec["n"] and not spec["n_param"]:
        try:
            count = int(body.get("count", 1))  # 還沒重新整理的舊網頁不會送 count
        except (TypeError, ValueError):
            raise ValueError("張數必須是整數") from None
        rule = spec["n"]
        if not rule["min"] <= count <= rule["max"]:
            raise ValueError(f"{spec['label']} 一次可以生成 {rule['min']}-{rule['max']} 張")
    parameters = clean_image_parameters(body.get("parameters") or {}, spec, "edit" if items else "generate")
    media, summaries = resolve_media(items, spec, session, dry_run)
    model = spec["edit"] if media else spec["generate"]
    payload = gmi_image.build_payload(prompt, parameters, [m["url"] for m in media])
    return spec, model, prompt, parameters, payload, summaries, count


def create_image_task(body):
    key = _keys["gmi"]["value"]
    if not key:
        raise ValueError("請先設定 GMI Cloud 的 API key")
    with api_session(key) as s:
        spec, model, prompt, parameters, payload, summaries, count = prepare_image_request(body, s)
    task = {
        # 同步模型要等圖片生成完才拿得到 GMI 的 request_id，先用本機的 ID，request_id 另外記
        "task_id": f"img-{uuid.uuid4().hex[:20]}",
        "kind": "image",
        "provider": "gmi",
        "model": model,
        "family": spec["id"],
        "created_at": time.time(),
        "prompt": prompt,
        "parameters": parameters,
        "media": summaries,
        "payload": payload,  # 沒拿到 request_id 時，靠它從 GMI 的請求列表找回
        "status": "IN_PROGRESS",
        "progress": "",
    }
    if not spec["n_param"]:  # 一次只生成一張的模型：記下張數，多張時每張各是一個請求，記在 parts
        task["count"] = count
        if count > 1:
            task.update(parts=[{} for _ in range(count)], progress=f"0/{count} 張")
    record = store.add(task)
    start_poller(task["task_id"])
    return record


def _run_image(task_id):
    """圖片任務：送出並等生成完 → 下載。伺服器重啟或按「重新查詢」時，從還沒完成的步驟接著做。
    多張的任務（parts）每張各是一個請求，見 _run_image_parts。"""
    record = store.get(task_id)
    if record is None:
        return
    key = _keys["gmi"]["value"]
    if not key:
        store.update(task_id, polling=False, error="還沒有 GMI Cloud 的 API key，設定後會自動繼續")
        return
    store.update(task_id, polling=True, error="")
    if record.get("parts"):
        _run_image_parts(task_id, key)
        return
    current, save = _record_access(task_id)

    def on_update(status, task, elapsed):
        fields = {"status": status}
        if status in FAILED:
            fields["finished_at"] = time.time()
        save(**fields)

    try:
        if not (record.get("status") == "SUCCESS" and record.get("result_urls")):
            with api_session(key) as s:
                result = _image_result(s, current, save, on_update)
            family = image_family(result.get("model"))
            if record.get("imported") and not family:  # 在圖片模式貼了影片的 request_id
                raise gmi_image.RequestFailed(f"這是 {result.get('model')} 的請求，不是圖片：請切到「影片」再用 ID 查詢")
            urls = gmi_image.image_urls(result)
            if not urls:
                raise RuntimeError(f"GMI 回報成功，但沒有圖片網址：{str(result.get('outcome'))[:300]}")
            fields = {"status": "SUCCESS", "result_urls": urls, "finished_at": time.time()}
            usage = (result.get("outcome") or {}).get("request_usage")  # OpenAI 回報的 token 用量
            if isinstance(usage, dict):
                fields["usage"] = usage
            if family:  # 用 ID 查詢時選的模型不一定對，以 GMI 回傳的為準
                fields.update(model=result["model"], family=family["id"])
            payload = result.get("payload")
            if record.get("imported") and isinstance(payload, dict):
                fields["prompt"] = str(payload.get("prompt") or "")
                fields["parameters"] = {k: payload[k] for k in IMAGE_PARAM_KEYS if k in payload}
                # 參考圖：任務列表靠它顯示縮圖、分辨改圖還是文字生圖（Gemini 兩種都是同一個模型 ID）
                refs = payload.get("image") or []
                refs = [refs] if isinstance(refs, str) else refs
                fields["media"] = [{"type": "reference_image", "url": u, "name": urlparse(u).path.rsplit("/", 1)[-1] or u}
                                   for u in refs if isinstance(u, str) and urlparse(u).scheme in ("http", "https")]
            record = store.update(task_id, **fields)
            if record is None:
                return
        store.update(task_id, downloading=True)
        files, folder, note = download_images(record.get("request_id") or task_id, record.get("result_urls") or [],
                                              image_format(record.get("parameters")))
        store.update(task_id, files=files, dir=folder_field(folder), notice=note, downloading=False, polling=False)
    except _TaskRemoved:
        pass
    except gmi_image.RequestFailed as e:
        fields = {"status": "FAILED", "finished_at": time.time()}
        if e.request_id:
            fields["request_id"] = e.request_id
        store.update(task_id, polling=False, error=explain_image_failure(str(e), task_spec(task_id)), **fields)
    except (RuntimeError, TimeoutError, requests.RequestException, OSError, ValueError) as e:
        store.update(task_id, polling=False, downloading=False,
                     error=explain_image_failure(friendly_error(e), task_spec(task_id)))


def _run_image_parts(task_id, key):
    """多張的任務（模型一次只生成一張：Gemini、Seedream）：同一個請求送出「張數」次，最多同時 IMAGE_PARALLEL 個。
    每張各自送出（或找回、接著查）→ 下載，做完一張就顯示一張；全部結束後整理成功、失敗的張數。
    失敗的張不重送；查詢中斷的張，按「重新查詢」或重新啟動時接著查。"""
    record = store.get(task_id)
    if record is None:
        return
    todo = [i for i, p in enumerate(record["parts"]) if not p.get("files") and p.get("status") not in FAILED]
    if todo:
        with ThreadPoolExecutor(max_workers=min(IMAGE_PARALLEL, len(todo))) as pool:
            list(pool.map(lambda i: _run_part(task_id, i, key), todo))
    record = store.get(task_id)
    if record is None:
        return
    parts = record["parts"]
    failed = [p for p in parts if not p.get("files") and p.get("status") in FAILED]
    stuck = [p for p in parts if not p.get("files") and p.get("status") not in FAILED]
    done = len(parts) - len(failed) - len(stuck)
    notes = []
    if failed:
        reason = failed[0].get("error") or "原因不明"
        notes.append(f"{len(parts)} 張中有 {len(failed)} 張失敗：{reason}" if done or stuck else reason)
    if stuck:
        notes.append(f"有 {len(stuck)} 張還沒完成：{stuck[0].get('error') or '查詢中斷'}\n按「重新查詢」會接著查")
    fields = {"polling": False, "error": "\n".join(notes)}
    if not stuck:
        fields.update(status="SUCCESS" if done else "FAILED", finished_at=time.time())
    store.update(task_id, **fields)


def _run_part(task_id, index, key):
    """多張任務的第 index 張：送出（或找回、接著查）→ 下載，結果記在 parts[index]。"""
    current, save = _part_access(task_id, index)

    def on_update(status, task, elapsed):
        save(status=status)

    def finish(**fields):  # 記下失敗原因；任務已經移除就算了
        try:
            save(**fields)
        except _TaskRemoved:
            pass

    try:
        part = current()
        if not (part.get("status") == "SUCCESS" and part.get("result_urls")):
            with api_session(key) as s:
                result = _image_result(s, current, save, on_update)
            urls = gmi_image.image_urls(result)
            if not urls:
                raise RuntimeError(f"GMI 回報成功，但沒有圖片網址：{str(result.get('outcome'))[:300]}")
            fields = {"status": "SUCCESS", "result_urls": urls}
            usage = (result.get("outcome") or {}).get("request_usage")
            if isinstance(usage, dict):
                fields["usage"] = usage
            save(**fields)
            part = current()
        files, folder, note = download_images(part["request_id"], part["result_urls"], image_format(part["parameters"]))
        save(files=files, dir=folder_field(folder), notice=note, error="")
    except _TaskRemoved:
        pass
    except gmi_image.RequestFailed as e:
        fields = {"status": "FAILED", "error": explain_image_failure(str(e), task_spec(task_id))}
        if e.request_id:
            fields["request_id"] = e.request_id
        finish(**fields)
    except (RuntimeError, TimeoutError, requests.RequestException, OSError, ValueError) as e:
        finish(error=explain_image_failure(friendly_error(e), task_spec(task_id)))
    except Exception as e:  # 程式的錯：記在這張上，其他張照常做完，整筆任務才不會一直停在「生成中」
        traceback.print_exc()
        finish(error=f"發生預料外的錯誤：{e!r}")


def _record_access(task_id):
    """單一請求的任務：回傳 (current, save)。current() 是整筆紀錄，save(**fields) 更新它；任務已經移除時丟 _TaskRemoved。
    _image_result、_recover_image 透過這兩個函式讀寫，多張的任務每張用 _part_access。"""
    def current():
        record = store.get(task_id)
        if record is None:
            raise _TaskRemoved
        return record

    def save(**fields):
        if store.update(task_id, **fields) is None:
            raise _TaskRemoved
    return current, save


def _part_access(task_id, index):
    """多張任務的第 index 張：current() 是那張的紀錄（request_id、submitted_at、status、files、dir…）加上整筆共用的
    model、payload、parameters、created_at；save(**fields) 只更新那張，順便整理整筆的 files（照張的順序）、進度，
    和輸出資料夾不能用時的提醒（notice）。"""
    def current():
        record = store.get(task_id)
        if record is None:
            raise _TaskRemoved
        shared = {k: record.get(k) for k in ("model", "payload", "parameters", "created_at")}
        return {**record["parts"][index], **shared}

    def save(**fields):
        def apply(record):
            parts = list(record["parts"])  # 換成新的 list、dict，正在把舊的轉成 JSON 的執行緒不受影響
            parts[index] = {**parts[index], **fields}
            done = sum(1 for p in parts if p.get("files") or p.get("status") in FAILED)
            return {"parts": parts, "files": [f for p in parts for f in p.get("files") or []],
                    "progress": f"{done}/{len(parts)} 張", "notice": next((p["notice"] for p in parts if p.get("notice")), "")}
        if store.mutate(task_id, apply) is None:
            raise _TaskRemoved
    return current, save


class _SubmitGate:
    """送出請求和從請求列表找回請求不能同時進行。payload 相同的請求（多張任務的每一張，或內容一樣的兩個任務）在列表裡
    分不出是誰的：找回時要等正在送出、還沒拿到 request_id 的都回應了，找的期間也不能有新的送出，才不會認領到別人的請求。"""

    def __init__(self):
        self.cond = threading.Condition()
        self.sending = 0
        self.recovering = False

    @contextmanager
    def send(self):
        with self.cond:
            self.cond.wait_for(lambda: not self.recovering)
            self.sending += 1
        try:
            yield
        finally:
            with self.cond:
                self.sending -= 1
                self.cond.notify_all()

    @contextmanager
    def recover(self):
        with self.cond:
            self.cond.wait_for(lambda: not self.recovering)
            self.recovering = True
            self.cond.wait_for(lambda: self.sending == 0)
        try:
            yield
        finally:
            with self.cond:
                self.recovering = False
                self.cond.notify_all()


_submit_gate = _SubmitGate()


def _image_result(session, current, save, on_update):
    """回傳成功的 GMI 請求物件：還沒送出就送出並等結果；有 request_id 就查到完成為止；
    送出後沒拿到 request_id（連線中斷、伺服器中途關閉）就從請求列表找回，不重送，免得重複扣款。
    current()、save(**fields) 讀寫這個請求的紀錄：整筆任務，或多張任務的其中一張（見 _record_access、_part_access）。"""
    record = current()
    request_id = record.get("request_id")
    if not request_id and not record.get("submitted_at"):
        save(submitted_at=time.time())
        try:
            with _submit_gate.send():
                result = gmi_image.create(session, record["model"], record["payload"], timeout=IMAGE_TIMEOUT)
                save(request_id=result["request_id"])
        except gmi_image.LostResponse as e:
            request_id = _recover_image(session, current, save, str(e))
        else:
            if gmi_video.STATUS.get(str(result.get("status", "")).lower()) == "SUCCESS":
                return result
            request_id = result["request_id"]  # 非同步模型（Seedream）：照影片的方式查到完成
    elif not request_id:
        request_id = _recover_image(session, current, save, "伺服器在等圖片生成時關閉了")
    return gmi_video.wait_for_task(session, request_id, timeout=POLL_TIMEOUT, interval=5, on_update=on_update,
                                   model=record["model"])


def _recover_image(session, current, save, reason):
    """送出後沒拿到 request_id：到 GMI 的請求列表找 payload 相同、還沒被任何任務認領的請求，找到就記下並回傳 request_id。"""
    record = current()
    since = record.get("submitted_at") or record["created_at"]
    with _submit_gate.recover():
        for attempt in range(4):  # 請求可能要一下子才出現在列表裡
            if attempt:
                time.sleep(10)
            found = gmi_image.find_by_payload(session, record["model"], record["payload"], since, claimed_request_ids())
            if found:
                save(request_id=found["request_id"])
                return found["request_id"]
    # 當成失敗（不再自動重試）：請求沒建立，下次啟動再找也找不到
    raise gmi_image.RequestFailed(f"{reason}，GMI 的請求列表裡也找不到這個請求，應該沒有建立成功，可以重新送出")


def claimed_request_ids():
    """所有任務（含多張任務的每一張）已經記下的 GMI request_id。"""
    ids = set()
    for t in store.all():
        ids.add(t.get("request_id"))
        ids.update(p.get("request_id") for p in t.get("parts") or [])
    ids.discard(None)
    return ids


def image_format(parameters):
    """參數指定的輸出格式（GPT Image、Seedream 叫 output_format，Gemini 叫 image_output_format），下載時認不出檔案類型才用。"""
    parameters = parameters or {}
    return parameters.get("output_format") or parameters.get("image_output_format")


def output_dir():
    """選項的輸出資料夾（沒選過是專案的 outputs/）。"""
    custom = _settings.get("outputs_dir")
    return Path(custom) if custom else OUTPUTS


def folder_field(folder):
    """任務紀錄的 dir 欄位：檔案存在專案的 outputs/ 時不記（專案資料夾搬了也找得到），其他資料夾記完整路徑。"""
    return None if folder == OUTPUTS else str(folder)


def folder_error(e):
    """資料夾不能用的原因，給使用者看的。"""
    if isinstance(e, FileNotFoundError):
        return "找不到資料夾，可能是外接硬碟沒接上，或資料夾被移走了"
    if isinstance(e, PermissionError):
        return "沒有權限寫入"
    if isinstance(e, (FileExistsError, NotADirectoryError)):
        return "同名的項目不是資料夾"
    return e.strerror or str(e)


def fallback_note(folder, e):
    return f"輸出資料夾 {folder} 無法使用（{folder_error(e)}），這次存到專案的 outputs/"


def ensure_folder(folder):
    """資料夾不存在就建立：上一層要已經存在，外接硬碟沒接上時才不會建到別的地方。同名的不是資料夾、沒有權限時丟 OSError。
    用 stat 判斷而不用 is_dir()：沒有權限時 is_dir() 在某些 Python 版本會回傳 False，被當成不存在。"""
    try:
        mode = folder.stat().st_mode
    except FileNotFoundError:
        folder.mkdir()
        return
    if not stat.S_ISDIR(mode):
        raise NotADirectoryError(str(folder))


def save_folder():
    """現在下載的影片、圖片要存到哪裡，回傳 (資料夾, 提醒)：選項的輸出資料夾不能用時（外接硬碟沒接上…）改存專案的 outputs/。
    生成結果的網址會過期，不能因為資料夾的問題就讓付過錢的結果下載失敗。"""
    folder = output_dir()
    if folder == OUTPUTS:
        return OUTPUTS, ""
    try:
        ensure_folder(folder)  # 資料夾被刪掉了就重新建立
    except OSError as e:
        return OUTPUTS, fallback_note(folder, e)
    return folder, ""


def save_output(save):
    """save(資料夾) 把檔案存進資料夾並回傳結果；回傳 (結果, 資料夾, 提醒)。
    存不進選項的輸出資料夾時（沒有權限、磁碟滿了…）改存專案的 outputs/，提醒記在任務上。"""
    folder, note = save_folder()
    try:
        return save(folder), folder, note
    except OSError as e:
        if folder == OUTPUTS or isinstance(e, requests.RequestException):  # 下載本身失敗（requests 的錯誤也是 OSError）
            raise
        return save(OUTPUTS), OUTPUTS, fallback_note(folder, e)


def recorded_folder(task, name):
    """存檔時記下的資料夾：多張的任務記在每一張（parts），其他記在任務上；沒記的是專案的 outputs/。"""
    for part in task.get("parts") or []:
        if name in (part.get("files") or []):
            return Path(part["dir"]) if part.get("dir") else OUTPUTS
    return Path(task["dir"]) if task.get("dir") else OUTPUTS


def locate(task, name):
    """任務的檔案在哪裡（找不到是 None）：先找存檔時記下的資料夾，再找目前的輸出資料夾和專案的 outputs/，
    使用者自己把舊檔案搬到新的輸出資料夾也找得到。"""
    for folder in dict.fromkeys((recorded_folder(task, name), output_dir(), OUTPUTS)):
        path = folder / name
        try:
            if path.is_file():
                return path
        except OSError:  # 沒有權限、網路磁碟斷線…
            pass
    return None


def find_output(rel):
    """網頁用 /outputs/<rel> 取的檔案（找不到是 None）：專案 outputs/ 裡的（素材副本、存在預設資料夾的結果），
    或存在其他輸出資料夾的任務檔案（只給任務紀錄裡有的檔名）。"""
    target = (OUTPUTS / rel).resolve()
    if target.is_relative_to(OUTPUTS.resolve()) and target.is_file():
        return target
    if rel and not re.search(r"[\\/:]", rel):
        for task in store.all():
            if rel == task.get("file") or rel in (task.get("files") or []):
                return locate(task, rel)
    return None


def download_images(base, urls, fmt=None):
    """把一個請求生成的圖片存到輸出資料夾，檔名用 GMI 的 request_id（一次多張時加 -1、-2…）；已經下載過的不重下。
    回傳 (檔名, 資料夾, 提醒)，見 save_output。"""
    base = safe_name(base)

    def save(folder):
        files = []
        for i, url in enumerate(urls, 1):
            stem = base if len(urls) == 1 else f"{base}-{i}"
            path = next((p for p in (folder / f"{stem}.{ext}" for ext in ("png", "jpg", "webp")) if p.exists()), None)
            if not path:
                if urlparse(url).scheme not in ("http", "https"):
                    raise RuntimeError(f"圖片網址不正確：{url[:300]}")
                path = gmi_image.download(url, folder, stem, fmt)
            files.append(path.name)
        return files
    return save_output(save)


def task_spec(task_id):
    """圖片任務用的是 image_models.py 的哪個模型（找不到時是 None）。"""
    record = store.get(task_id) or {}
    return IMAGE_SPECS.get(record.get("family")) or image_family(record.get("model"))


def explain_image_failure(text, spec=None):
    """圖片任務常見的失敗原因加上中文說明。GPT Image 2 會說明原因，2.5 一律回 Generation rejected；
    Gemini 被 Google 擋下時，訊息裡有 Vertex AI 的 finishReason／blockReason（IMAGE_SAFETY、PROHIBITED_CONTENT…）。"""
    if re.search(r"failed to fetch image|Failed to download media", text, re.I):
        return f"模型供應商下載不到參考圖：網址打不開、要登入才能看，或已經過期（失敗不收費）。\n原始訊息：{text}"
    if re.search(r"Backend error \(40\d\)", text):  # Seedream（BytePlus）在送出時就拒絕，GMI 不轉告原因
        return ("BytePlus 拒絕了這個請求，GMI 沒有轉告原因（請求沒有建立，不收費）。常見原因：參考圖網址打不開、"
                f"提示詞或參考圖沒通過審核，或尺寸不被接受。\n原始訊息：{text}")
    m = re.search(r"(Input|Output)(Text|Image)SensitiveContentDetected", text)
    if m:  # Seedream（BytePlus）的內容審核
        what = {("Input", "Text"): "提示詞", ("Input", "Image"): "參考圖", ("Output", "Image"): "生成的圖片",
                ("Output", "Text"): "生成的內容"}[m.groups()]
        return (f"BytePlus 判定{what}可能含有敏感內容，拒絕生成（失敗不收費）。"
                f"請改寫提示詞或換參考圖再試。\n原始訊息：{text}")
    if re.search(r"safety system|moderation_blocked|content policy", text, re.I):
        return f"提示詞或參考圖沒通過 OpenAI 的內容審核，請改寫後再試。\n原始訊息：{text}"
    if re.search(r"IMAGE_SAFETY|PROHIBITED_CONTENT|BLOCKLIST|SPII|RECITATION|blockReason|finishReason\W+SAFETY", text):
        return ("提示詞或參考圖沒通過 Google 的安全審核（例如真人肖像、名人、暴力或受版權保護的內容），"
                f"請改寫提示詞或換參考圖再試。\n原始訊息：{text}")
    if re.search(r"Generation rejected|INVALID_INPUT", text):
        tip = "可以改寫提示詞，或勾選「寬鬆審核」再試" if spec and spec["moderation"] else "可以改寫提示詞再試"
        return (f"GMI 拒絕了這個請求。常見原因：提示詞或參考圖沒通過內容審核（{tip}）、"
                f"參考圖網址打不開，或參數組合不被接受。\n原始訊息：{text}")
    return text


def start_poller(task_id):
    with _pollers_lock:
        thread = _pollers.get(task_id)
        if thread and thread.is_alive():
            return
        record = store.get(task_id)
        target = _run_image if record and record.get("kind") == "image" else _poll
        thread = threading.Thread(target=target, args=(task_id,), name=f"poll-{task_id}", daemon=True)
        _pollers[task_id] = thread
        thread.start()


class _TaskRemoved(Exception):
    pass


def _poll(task_id):
    record = store.get(task_id)
    if record is None:
        return
    provider = record.get("provider") or "mixroute"
    if provider not in PROVIDERS:
        store.update(task_id, polling=False, error=f"不支援的 API：{provider}")
        return
    key = _keys[provider]["value"]
    if not key:
        store.update(task_id, polling=False, error=f"還沒有 {PROVIDERS[provider]['label']} 的 API key，設定後會自動繼續查詢")
        return
    model = record.get("model") or DEFAULT_MODEL
    store.update(task_id, polling=True, error="")

    def on_update(status, task, elapsed):
        fields = {"status": status, "progress": task.get("progress") or ""}
        if status in FAILED:
            fields["finished_at"] = time.time()
        if provider == "gmi" and task.get("model") in gmi_video.MODELS and task["model"] != model:
            fields["model"] = task["model"]  # 用 ID 查詢時選的模型不一定對，以 GMI 回傳的為準
        if store.update(task_id, **fields) is None:
            raise _TaskRemoved  # 使用者從列表移除了，不用再查

    try:
        with api_session(key) as s:
            if provider == "gmi":
                task = gmi_video.wait_for_task(s, task_id, timeout=POLL_TIMEOUT, on_update=on_update, model=model)
            else:
                task = mixroute_video.wait_for_task(s, task_id, timeout=POLL_TIMEOUT, on_update=on_update)
        if provider == "gmi":
            video_url, usage = gmi_video.video_url(task), None
        else:
            video_url, usage = task.get("result_url", ""), (task.get("data") or {}).get("usage")
        record = store.update(task_id, result_url=video_url, usage=usage)
        if record is None:
            return
        if not record.get("finished_at"):
            store.update(task_id, finished_at=time.time())
        if urlparse(video_url).scheme not in ("http", "https"):
            raise RuntimeError(f"任務成功但沒有有效的影片網址：{video_url[:300]}")
        name = f"{safe_name(task_id)}.mp4"
        path, note = locate(record, name), record.get("notice") or ""
        if path is None:
            store.update(task_id, downloading=True)
            path, _, note = save_output(lambda folder: mixroute_video.download(video_url, folder / name))
        store.update(task_id, file=name, dir=folder_field(path.parent), notice=note, downloading=False, polling=False)
    except _TaskRemoved:
        pass
    except TimeoutError:
        store.update(task_id, polling=False, error=f"等了 {POLL_TIMEOUT // 3600} 小時仍未完成，已停止自動查詢，可按「重新查詢」")
    except (RuntimeError, requests.RequestException, OSError, ValueError) as e:
        store.update(task_id, polling=False, downloading=False, error=explain_failure(friendly_error(e), store.get(task_id) or record))


def explain_failure(text, record):
    """常見的失敗原因加上中文說明。"""
    if "Failed to download media" in text:
        return f"模型供應商下載不到素材：網址打不開、要登入才能看，或臨時連結已經過期（失敗不收費）。\n原始訊息：{text}"
    m = re.search(r"input (?:image|video)s? ((?:'content\[\d+\]'\s*)+)may contain real person", text)
    if not m:
        return text
    # content[0] 是提示詞，content[1] 起依序是送出的素材（從 GMI 後台的失敗紀錄推得：編號都落在參考圖片的範圍內）
    spec = SPECS.get((record.get("provider") or "mixroute", record.get("model") or DEFAULT_MODEL)) or video_models.GMI_SEEDANCE_25
    counters, names = Counter(), []
    for item in record.get("media") or []:
        typ = item.get("type")
        counters[typ] += 1
        slot = {"reference_image": "image", "reference_video": "video", "reference_audio": "audio"}.get(typ)
        names.append(f"{spec['labels'][slot]}{counters[typ]}" if slot else MEDIA_NAMES.get(typ, typ))
    indexes = [int(i) for i in re.findall(r"content\[(\d+)\]", m.group(1))]
    if all(0 < i <= len(names) for i in indexes):
        where = f"推測是 {'、'.join(names[i - 1] for i in indexes)}"
    else:  # 用 ID 查詢的任務沒有素材清單
        where = f"第 {'、'.join(str(i) for i in indexes)} 個素材"
    return (f"BytePlus 判定素材可能含有真人（{where}），拒絕生成。Seedance 不接受有擬真人臉的素材（AI 生成的擬真人臉也會被擋），"
            f"請換成插畫、卡通風格或沒有人臉的素材再試（失敗不收費）。\n原始訊息：{text}")


def resume_pending(provider=None):
    """伺服器重啟或設定 key 後，把還沒完成（或還沒下載）的任務接著查；有給 provider 就只查那邊的。"""
    for task in store.all():
        if provider and (task.get("provider") or "mixroute") != provider:
            continue
        if task.get("status") in FAILED:
            continue
        if task.get("file") and locate(task, task["file"]):
            continue
        files = task.get("files")  # 圖片任務；多張的任務做到一半時也有 files，要等狀態是成功才算完成
        if files and task.get("status") == "SUCCESS" and all(locate(task, f) for f in files):
            continue
        start_poller(task["task_id"])


def idle_watchdog(server, idle):
    """網頁開著時每隔幾秒就會來查任務；超過 idle 秒沒人來、也沒有進行中的任務，就結束伺服器。"""
    while True:
        time.sleep(min(30, max(1, idle / 5)))
        if _restart_status:  # 已經交給重新啟動的新程序（Windows 上這個程序還在等它結束）
            return
        with _pollers_lock:
            busy = any(t.is_alive() for t in _pollers.values())
        if not busy and time.monotonic() - _last_request > idle:
            desc = f"{idle // 60} 分鐘" if idle >= 60 else f"{idle} 秒"
            print(f"網頁已關閉超過 {desc}，也沒有進行中的任務，自動結束。", flush=True)
            server.shutdown()
            return


def valid_setting(name, value):
    if name == "outputs_dir":
        return value is None or (isinstance(value, str) and os.path.isabs(value))
    choices = SETTING_CHOICES.get(name)
    return choices is not None and type(value) is type(choices[0]) and value in choices


def load_settings():
    """讀 outputs/settings.json：壞掉或不認得的值用預設；不認得的欄位（例如新版才有的選項）照樣保留。"""
    settings = dict(DEFAULT_SETTINGS)
    try:
        saved = json.loads(SETTINGS_FILE.read_text("utf-8"))
    except FileNotFoundError:
        return settings
    except (OSError, ValueError) as e:
        print(f"讀不懂 {SETTINGS_FILE.name}（{e}），先用預設的選項")
        return settings
    if isinstance(saved, dict):
        settings.update((k, v) for k, v in saved.items() if k not in DEFAULT_SETTINGS or valid_setting(k, v))
    return settings


def probe_write(folder):
    """在資料夾裡建一個暫存檔再刪掉，確定寫得進去（macOS 的「桌面」「文件」等資料夾第一次寫入時會詢問權限）。"""
    probe = folder / f".video_ui-{uuid.uuid4().hex[:8]}.tmp"
    probe.write_bytes(b"")
    probe.unlink()


def no_permission_text(folder):
    text = f"沒有權限寫入 {folder}"
    if sys.platform == "darwin":
        text += ("。在「桌面」「文件」「下載項目」、iCloud 雲碟或外接硬碟裡的資料夾，macOS 會先詢問能不能取用，拒絕過的話請到"
                 "「系統設定 › 隱私權與安全性 › 檔案與檔案夾」允許「AI 影片生成」（從終端機啟動的是「終端機」），或改選其他資料夾")
    return text


def check_output_folder(value):
    """使用者選的輸出資料夾：整理成完整路徑，確定能用（不存在就建立，上一層要已經存在；要寫得進去）。
    None 或選了專案的 outputs/ 就是預設，回傳 None。"""
    if value is None:
        return None
    text = value.strip() if isinstance(value, str) else ""
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":  # Windows 的「複製路徑」會加上引號
        text = text[1:-1].strip()
    if not text:
        raise ValueError("請輸入資料夾路徑")
    text = os.path.expanduser(text)
    if not os.path.isabs(text):
        example = "D:\\AI 影片" if os.name == "nt" else str(Path.home() / "Movies" / "AI 影片")
        raise ValueError(f"請輸入完整路徑，例如 {example}")
    folder = Path(os.path.normpath(text))
    try:
        try:
            folder.stat()
        except FileNotFoundError:
            if not folder.parent.is_dir():
                raise ValueError(f"找不到 {folder.parent}，請選已經存在的資料夾") from None
        ensure_folder(folder)
        if os.path.samefile(folder, OUTPUTS):
            return None
        probe_write(folder)
    except PermissionError:
        raise ValueError(no_permission_text(folder)) from None
    except OSError as e:
        raise ValueError(f"無法使用 {folder}：{folder_error(e)}") from None
    return str(folder)


def folder_problem(folder):
    """輸出資料夾現在能不能用：能用是空字串，不能用是原因（這時新的檔案先存到專案的 outputs/）。
    資料夾被刪掉、上一層還在的話，下次存檔時會重新建立，也算能用。"""
    try:
        if not stat.S_ISDIR(folder.stat().st_mode):
            return folder_error(NotADirectoryError())
        probe_write(folder)
        return ""
    except FileNotFoundError:
        try:
            if folder.parent.is_dir():
                return ""
        except OSError:
            pass
        return folder_error(FileNotFoundError())
    except OSError as e:
        return folder_error(e)


def storage_status():
    """選項頁「輸出資料夾」的狀態。"""
    custom = _settings.get("outputs_dir")
    return {"dir": custom or str(OUTPUTS), "default": str(OUTPUTS), "custom": custom,
            "problem": folder_problem(Path(custom)) if custom else "", "picker": picker_command(OUTPUTS) is not None}


def picker_command(start):
    """跳出系統選擇資料夾視窗的 (指令, 要加的環境變數, 表示「按了取消」的結束代碼, 路徑是否 base64)；這台電腦沒有可用的是 None。
    macOS、Windows 按取消時正常結束、不輸出；Linux 的 zenity、kdialog 按取消時結束代碼是 1。"""
    if sys.platform == "darwin":
        return ["osascript", "-l", "JavaScript", "-e", MAC_PICKER, PICK_PROMPT, "選擇", str(start)], {}, (), False
    if os.name == "nt":
        script = base64.b64encode(WIN_PICKER.encode("utf-16-le")).decode()
        env = {"VIDEO_UI_PICK_PROMPT": PICK_PROMPT, "VIDEO_UI_PICK_START": str(start)}
        return ["powershell.exe", "-NoProfile", "-STA", "-EncodedCommand", script], env, (), True
    if shutil.which("zenity"):
        return ["zenity", "--file-selection", "--directory", f"--title={PICK_PROMPT}", f"--filename={start}/"], {}, (1,), False
    if shutil.which("kdialog"):
        return ["kdialog", "--title", PICK_PROMPT, "--getexistingdirectory", str(start)], {}, (1,), False
    return None


def pick_folder():
    """跳出系統的選擇資料夾視窗並等使用者選好：回傳選的資料夾，按了取消（或選項頁按了取消）是 None。"""
    global _picker
    start = output_dir()
    try:
        start = start if start.is_dir() else OUTPUTS
    except OSError:
        start = OUTPUTS
    command = picker_command(start)
    if not command:
        raise ValueError("這台電腦沒辦法跳出選擇資料夾的視窗，請直接輸入資料夾路徑")
    argv, env, cancel_codes, encoded = command
    with _picker_lock:
        if _picker and _picker.poll() is None:
            raise ValueError("選擇資料夾的視窗已經開著了，可能被其他視窗擋住")
        try:
            # Windows 的伺服器在背景執行（沒有主控台），不加 CREATE_NO_WINDOW 會多跳一個黑色視窗
            proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    env={**os.environ, **env} if env else None,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as e:
            raise ValueError(f"無法打開選擇資料夾的視窗（{e.strerror or e}），請直接輸入資料夾路徑") from None
        proc.canceled = False
        _picker = proc
    out, err = proc.communicate()
    with _picker_lock:
        if _picker is proc:
            _picker = None
    lines = out.decode("utf-8", "replace").strip().splitlines()
    text = lines[-1].strip() if lines else ""
    if proc.canceled or proc.returncode in cancel_codes or (proc.returncode == 0 and not text):
        return None
    if proc.returncode:
        detail = err.decode("utf-8", "replace").strip()[-300:] or f"結束代碼 {proc.returncode}"
        raise ValueError(f"選擇資料夾的視窗出了問題（{detail}），請直接輸入資料夾路徑")
    if encoded:
        try:
            text = base64.b64decode(text, validate=True).decode("utf-8")
        except ValueError:
            raise ValueError("讀不懂選擇資料夾的視窗傳回的路徑，請直接輸入資料夾路徑") from None
    return text


def cancel_picker():
    """關掉開著的選擇資料夾視窗：選項頁按了取消，或伺服器要結束了。"""
    with _picker_lock:
        proc = _picker
        if proc and proc.poll() is None:
            proc.canceled = True
            proc.terminate()


def reveal(path, select=True):
    """在 Finder／檔案總管顯示：select 為真時選取這個檔案，不然打開這個資料夾。"""
    if sys.platform == "darwin":
        subprocess.run(["open", "-R", str(path)] if select else ["open", str(path)], check=False)
    elif sys.platform == "win32":
        subprocess.run(["explorer", "/select,", str(path)] if select else ["explorer", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path.parent if select else path)], check=False)


def save_settings(changes):
    if "outputs_dir" in changes:  # 先確定資料夾能用；macOS 可能要等使用者回答要不要允許取用，不在鎖裡做
        changes = {**changes, "outputs_dir": check_output_folder(changes["outputs_dir"])}
    with _settings_lock:
        new = dict(_settings)
        for name, value in changes.items():
            if not valid_setting(name, value):
                raise ValueError(f"不支援的選項：{name} = {value!r}")
            new[name] = value
        tmp = SETTINGS_FILE.with_name(SETTINGS_FILE.name + ".tmp")
        tmp.write_text(json.dumps(new, ensure_ascii=False, indent=1), "utf-8")
        os.replace(tmp, SETTINGS_FILE)
        _settings.update(new)
        return dict(_settings)


def check_update(apply, quick=False):
    """檢查（apply=True 時並更新）GitHub 上的新版，結果記在 _update 給選項頁顯示。"""
    global _update
    with _update_lock:
        _update = updater.run(apply, quick=quick)
        return _update


def image_waiting():
    """還有請求在等 GMI 同步回應（還沒有 request_id）的圖片任務：這時重新啟動只能靠請求列表找回，手動更新前先等它們完成。
    多張的任務看每一張。"""
    with _pollers_lock:
        alive = {task_id for task_id, t in _pollers.items() if t.is_alive()}
    return [t for t in store.all() if t["task_id"] in alive and t.get("kind") == "image"
            and any(not r.get("request_id") and r.get("status") not in FAILED for r in t.get("parts") or [t])]


def request_restart(server, status):
    """選項頁的「立即更新並重新啟動」：回應送出後停下伺服器，main() 接著重新啟動載入新版。"""
    global _restart_status
    _restart_status = status
    threading.Timer(0.3, server.shutdown).start()


def restart(status, no_browser=False):
    """用同樣的參數重新執行 video_ui.py 載入新版；更新結果透過環境變數交給新的程序，它就不用再檢查一次。
    進行中的影片任務會中斷查詢，新的程序啟動時照常接著查。"""
    os.environ[UPDATED_ENV] = json.dumps(status)
    argv = [sys.executable, *(getattr(sys, "orig_argv", None) or [sys.executable, *sys.argv])[1:]]
    if no_browser and "--no-browser" not in argv:
        argv.append("--no-browser")  # 網頁已經開著，重新啟動後它會自己重新整理
    print("重新啟動以載入新版本…", flush=True)
    sys.stderr.flush()
    if os.name == "nt":  # Windows 的 os.execv 會另開一個程序、原本的終端機接不回來，改成等新的程序結束
        if store:  # 等的時候這個程序的查詢執行緒還在跑：交棒後就不再寫 tasks.json
            store.close()
        # 輸出要明確交給新的程序：不指定時 Windows 不讓它繼承檔案 handle，背景執行（輸出導到記錄檔）時記錄會斷掉
        sys.exit(subprocess.call(argv, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr))
    os.execv(sys.executable, argv)


class Handler(BaseHTTPRequestHandler):
    server_version = "VideoUI/1.0"

    def log_request(self, code="-", size="-"):
        # 網頁每幾秒輪詢一次，成功的 GET 不印，免得洗版
        if self.command != "GET" or str(code)[:1] not in ("2", "3"):
            super().log_request(code, size)

    def do_GET(self):
        self._dispatch()

    def do_HEAD(self):
        self._dispatch()

    def do_POST(self):
        self._dispatch()

    def do_DELETE(self):
        self._dispatch()

    def _dispatch(self):
        global _last_request
        _last_request = time.monotonic()
        # 擋 DNS rebinding（Host 必須是本機）與其他網站的跨站請求（必須帶自訂標頭，會觸發 CORS 預檢而被擋）
        if (self.headers.get("Host") or "").lower() not in self.server.allowed_hosts:
            return self._send_json({"error": "forbidden"}, 403)
        if self.command in ("POST", "DELETE"):
            origin = self.headers.get("Origin")
            if (origin and origin.lower() not in self.server.allowed_origins) or self.headers.get("X-Video-UI") != "1":
                return self._send_json({"error": "forbidden"}, 403)
        path = urlparse(self.path).path
        try:
            self._route(self.command, path)
        except ValueError as e:
            self._send_json({"error": str(e)}, 400)
        except (RuntimeError, requests.RequestException, OSError) as e:
            self._send_json({"error": friendly_error(e)}, 502)
        except Exception as e:  # 程式錯誤也回 JSON，網頁才看得到原因
            traceback.print_exc()
            self._send_json({"error": f"伺服器錯誤：{e!r}"}, 500)

    def _route(self, method, path):
        if method in ("GET", "HEAD"):
            if path == "/":
                return self._send_html(head=method == "HEAD")
            if path == "/api/config":
                return self._send_json({
                    "keys": {name: k["source"] for name, k in _keys.items()},
                    "prices": _prices,
                    "model": mixroute_video.MODEL,  # 啟動器（launch.sh、windows/launcher.py）用這個欄位判斷伺服器是否已經在跑
                    "platform": sys.platform,
                    "outputs_dir": str(OUTPUTS),
                    "settings": _settings,
                    "version": _version,
                    "update": _update,
                })
            if path == "/api/tasks":
                # 選項也一起帶回去：在別的分頁或瀏覽器改了（例如關掉通知），開著的網頁跟著更新
                return self._send_json({"tasks": store.all(), "now": time.time(), "settings": _settings})
            if path == "/api/outputs-dir":
                return self._send_json({"storage": storage_status()})
            if path.startswith("/outputs/"):
                # 生成的檔案不一定在專案的 outputs/（選項可以換輸出資料夾），網址一樣是 /outputs/<檔名>，由 find_output 找
                target = find_output(unquote(path[len("/outputs/"):]))
                if target:
                    return self._send_file(target, head=method == "HEAD")
            return self._send_json({"error": "not found"}, 404)

        if method == "POST" and path == "/api/key":
            body = self._read_json()
            provider = provider_of(body.get("provider"))
            key = str(body.get("key") or "").strip()
            if not key:
                raise ValueError("請輸入 API key")
            warning = set_key(provider, key)
            return self._send_json({"ok": True, "warning": warning, "key_source": _keys[provider]["source"],
                                    "prices": _prices})
        if method == "POST" and path == "/api/settings":
            return self._send_json({"settings": save_settings(self._read_json())})
        if method == "POST" and path == "/api/outputs-dir":
            # 選項的輸出資料夾：{"pick": true} 跳出系統的選擇資料夾視窗（等使用者選好才回應）；{"cancel": true} 關掉那個視窗；
            # {"path": "…"} 直接指定路徑，null 是改回專案的 outputs/
            body = self._read_json()
            if body.get("cancel"):
                cancel_picker()
                return self._send_json({"ok": True})
            if body.get("pick"):
                chosen = pick_folder()
                if chosen is None:
                    return self._send_json({"canceled": True, "settings": _settings, "storage": storage_status()})
            elif "path" in body:
                chosen = body["path"]
            else:
                raise ValueError("請選擇或輸入資料夾")
            settings = save_settings({"outputs_dir": chosen})
            return self._send_json({"settings": settings, "storage": storage_status()})
        if method == "POST" and path == "/api/update":
            apply = bool(self._read_json().get("apply"))
            waiting = apply and image_waiting()
            if waiting:
                raise ValueError(f"有 {len(waiting)} 個圖片任務正在等 GMI 生成，完成後再更新（重新啟動會打斷等待）")
            status = check_update(apply)
            if status["state"] == "updated":
                request_restart(self.server, status)
            return self._send_json({"update": status, "restarting": status["state"] == "updated"})
        if method == "POST" and path == "/api/images":
            data = self._read_body(MAX_IMAGE_BYTES)
            ext = sniff_image(data)
            if not ext:
                raise ValueError("只接受 JPEG、PNG、WebP、BMP 圖片")
            return self._send_json({"ref": save_input(data, ext), "bytes": len(data)})
        if method == "POST" and path == "/api/upload":
            return self._send_json(self._upload())
        if method == "POST" and path == "/api/tasks":
            body = self._read_json()
            return self._send_json(create_image_task(body) if body.get("kind") == "image" else create_task(body))
        if method == "POST" and path == "/api/preview":
            body = self._read_json()
            if body.get("kind") == "image":  # count：同一個請求要送出幾次（一次只生成一張的模型要多張時）
                _, model, _, _, payload, _, count = prepare_image_request(body, dry_run=True)
                return self._send_json({"request": {"model": model, "payload": payload}, "count": count})
            spec, prompt, negative, parameters, media, _ = prepare_request(body, dry_run=True)
            return self._send_json({"request": request_json(spec, prompt, negative, parameters, media)})
        if method == "POST" and path == "/api/tasks/import":
            body = self._read_json()
            if body.get("kind") == "image":  # 先記成 generate，查到後以 GMI 回傳的模型為準
                spec = image_spec_of(body.get("model"))
                fields = {"kind": "image", "provider": "gmi", "model": spec["generate"], "family": spec["id"]}
            else:
                provider = provider_of(body.get("provider"))
                fields = {"provider": provider, "model": spec_of(provider, body.get("model"))["id"]}
            task_id = str(body.get("task_id") or "").strip()
            if not re.fullmatch(r"[\w.:-]{4,200}", task_id):
                raise ValueError("task_id 格式不正確")
            if fields.get("kind") == "image":
                fields["request_id"] = task_id
            if not store.get(task_id):
                store.add({"task_id": task_id, **fields, "created_at": time.time(), "imported": True,
                           "prompt": "", "parameters": {}, "media": [], "status": "QUEUED", "progress": ""})
            start_poller(task_id)
            return self._send_json(store.get(task_id))
        m = re.fullmatch(r"/api/tasks/([^/]+)(/refresh)?", path)
        if m:
            task_id = unquote(m.group(1))
            if not store.get(task_id):
                return self._send_json({"error": "找不到這個任務"}, 404)
            if method == "POST" and m.group(2):
                store.update(task_id, error="")
                start_poller(task_id)
                return self._send_json(store.get(task_id))
            if method == "DELETE" and not m.group(2):
                store.remove(task_id)  # 只移除紀錄，不刪影片檔
                return self._send_json({"ok": True})
        if method == "POST" and path == "/api/reveal":
            body = self._read_json()
            if body.get("folder"):  # 選項的「打開」：輸出資料夾（被刪掉了就重新建立）
                folder = output_dir()
                try:
                    ensure_folder(folder)
                except OSError as e:
                    raise ValueError(f"無法打開 {folder}：{folder_error(e)}") from None
                reveal(folder, select=False)
                return self._send_json({"ok": True})
            target = find_output(str(body.get("file") or ""))
            if not target:
                raise ValueError("找不到檔案，可能被移走或刪除了")
            reveal(target)
            return self._send_json({"ok": True})
        self._send_json({"error": "not found"}, 404)

    def _upload(self):
        kind = self.headers.get("X-Kind")
        if kind not in UPLOAD_RULES:
            raise ValueError("不支援的上傳類型")
        exts, limit = UPLOAD_RULES[kind]
        filename = unquote(self.headers.get("X-Filename") or "")
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        gmi = self.headers.get("X-Provider") == "gmi"
        if gmi and kind == "file":
            raise ValueError("GMI 不支援文件素材")
        if ext in ("doc", "docx"):
            raise ValueError("Litterbox 不接受 .doc/.docx，請轉成 PDF 或改貼網址")
        if ext not in exts:
            raise ValueError(f"只接受 {'、'.join(sorted(exts))} 檔")
        ttl = self.headers.get("X-TTL") if self.headers.get("X-TTL") in LITTERBOX_TTLS else "1h"
        name = save_input(self._read_body(limit), ext)
        # GMI：送出時才上傳到 GMI（那時一定有 key）；X-Defer：目前的模型用不到這個檔案（例如太長），先不傳 Litterbox
        if gmi or self.headers.get("X-Defer") == "1":
            return {"local": name}
        url, expires_at = litterbox_upload(name, ttl)
        return {"url": url, "local": name, "expires_at": expires_at, "ttl": ttl}

    def _read_body(self, limit):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            raise ValueError("沒有收到內容")
        if length > limit:
            self.close_connection = True
            raise ValueError(f"檔案太大（上限 {limit >> 20} MB）")
        return self.rfile.read(length)

    def _read_json(self):
        raw = self._read_body(MAX_JSON_BYTES)
        try:
            body = json.loads(raw)
        except ValueError:
            raise ValueError("請求內容不是 JSON") from None
        if not isinstance(body, dict):
            raise ValueError("請求內容格式不正確")
        return body

    def _send_json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _send_html(self, head=False):
        """網頁本身：把 video_models.py、image_models.py 的模型清單填進 __CATALOG__、__IMAGE_CATALOG__，
        網頁一載入就能畫出表單；選項的主題填進 __THEME__，一開始就是對的顏色，不會先閃一下。"""
        def as_json(models):
            return json.dumps(models, ensure_ascii=False).replace("</", "<\\/")
        data = (HTML_FILE.read_text("utf-8").replace("__THEME__", _settings["theme"], 1)
                .replace("__IMAGE_CATALOG__", as_json(image_models.MODELS), 1)
                .replace("__CATALOG__", as_json(video_models.MODELS), 1).encode())
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if not head:
            self.wfile.write(data)

    def _send_file(self, path, head=False):
        """支援 Range，Safari 播影片一定要有。"""
        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", (self.headers.get("Range") or "").strip())
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1))
                end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
            else:
                start = max(0, size - int(m.group(2)))
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = 206
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if ctype.startswith("text/"):
            ctype += "; charset=utf-8"
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Cache-Control", "no-cache")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if head:
            return
        try:
            with open(path, "rb") as f:
                f.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = f.read(min(1 << 16, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass  # 播放器拖動進度時會中斷舊的請求


def main():
    global store, _update, _version
    if os.name == "nt":  # 輸出導到記錄檔時（Windows 啟動器），Windows 用系統編碼寫檔（英文版是 cp1252），一印中文就當掉
        for stream in (sys.stdout, sys.stderr):
            if stream and not stream.isatty():
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    labels = dict.fromkeys(m["label"] for m in video_models.MODELS + image_models.MODELS)
    p = argparse.ArgumentParser(description=f"影片和圖片生成網頁介面（{'、'.join(labels)}）")
    p.add_argument("--port", type=int, default=8765, help="本機埠號（預設 8765）")
    p.add_argument("--no-browser", action="store_true", help="不要自動打開瀏覽器")
    p.add_argument("--idle-exit", type=int, default=0, metavar="SECONDS",
                   help="網頁關閉且沒有進行中的任務超過這麼多秒就自動結束（預設 0＝不自動結束）")
    args = p.parse_args()

    OUTPUTS.mkdir(exist_ok=True)
    _settings.update(load_settings())
    # 先佔住埠（確定沒有另一個 video_ui.py 在跑，才不會改到它正在用的檔案）再檢查更新；
    # 檢查完才開始接受連線，啟動器（launch.sh、windows/launcher.py）等到連得上才開網頁，所以打開的一定是新版
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler, bind_and_activate=False)
    # HTTPServer 預設開 SO_REUSEADDR，在 Windows 上它讓第二個 video_ui.py 也綁得上同一個埠，上面的保護就沒用了。
    # Windows 本來就能綁定還有 TIME_WAIT 連線的埠，不開也不影響重新啟動（socket.create_server 也是這樣處理）
    server.allow_reuse_address = os.name != "nt"
    try:
        server.server_bind()
    except OSError as e:
        server.server_close()
        sys.exit(f"無法使用埠 {args.port}（{e.strerror}）：可能已經開著一個 video_ui.py，"
                 "或用 --port 換一個（App 和 Windows 啟動器看環境變數 VIDEO_UI_PORT）")
    server.allowed_hosts = {f"127.0.0.1:{args.port}", f"localhost:{args.port}"}
    server.allowed_origins = {f"http://{h}" for h in server.allowed_hosts}
    just_updated = os.environ.pop(UPDATED_ENV, None)
    if just_updated:  # 剛更新完重新啟動
        try:
            _update = json.loads(just_updated)
        except ValueError:
            pass
    elif _settings["auto_update"]:
        print("檢查更新…", flush=True)
        status = check_update(apply=True, quick=True)
        print(f"檢查更新：{status['message']}" + (f"（{status['detail']}）" if status.get("detail") else ""), flush=True)
        if status["state"] == "updated":
            server.server_close()
            restart(status)
    _version = updater.current_version()
    store = TaskStore(TASKS_FILE)
    server.server_activate()

    url = f"http://127.0.0.1:{args.port}/"
    print(f"影片和圖片生成介面：{url}（Ctrl+C 結束）")
    for name, p in PROVIDERS.items():
        print(f"{p['label']} API key：" + (f"使用環境變數 {p['env']}" if _keys[name]["value"] else "未設定環境變數，請在網頁上輸入"))
    if _keys["gmi"]["value"]:  # 背景檢查環境變數的 GMI key 並更新價格，不拖慢啟動
        threading.Thread(target=check_env_gmi_key, daemon=True).start()
    resume_pending()
    if args.idle_exit > 0:
        threading.Thread(target=idle_watchdog, args=(server, args.idle_exit), daemon=True).start()
    if not args.no_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已關閉。未完成的任務下次啟動會接著查詢。")
    finally:
        server.server_close()
        cancel_picker()  # 選擇資料夾的視窗還開著的話一起關掉，不留在畫面上
    if _restart_status:
        restart(_restart_status, no_browser=True)


if __name__ == "__main__":
    main()
