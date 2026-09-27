"""GMI Cloud 的影片生成（request queue API）：上傳素材 → 建立請求 → 輪詢狀態。

文件：https://docs.gmicloud.ai/inference-engine/api-reference/video-api-reference
模型參數：GET {BASE_URL}/models/<model>

給 video_ui.py 用，介面和 mixroute_video 相同（create_task / wait_for_task），參數與 media 也沿用
mixroute_video 的格式，這裡再依模型轉成 GMI 的 payload（見 MODELS）。下載影片直接用 mixroute_video.download。
各模型的參數範圍與素材限制在 video_models.py。

wan3.0-video 和 MixRoute 的差異：
- 一律產生音軌（沒有 audio 參數）；時長只能 2-30 秒（沒有 -1 自動）；seed 只能 0-2147483647。
- 素材只能是公開網址，不收 base64、文件或網頁；本機檔案用 upload() 傳到 GMI 的儲存空間。
- 多了 negative_prompt；提示詞上限 5000 字。

seedance-2-5-260628（BytePlus Seedance 2.5）和 seedance-2-0-260128（Seedance 2.0）的 payload 格式相同：
- 首尾幀送字串（送陣列 GMI 會回 500 Backend error (403)），參考素材送陣列。
- 音軌開關叫 generate_audio；沒有 negative_prompt、prompt_extend，多了 web_search。
- GMI 建立請求時會依解析度、比例、時長預扣費用：算不出價格的組合（例如 2.5 的 duration -1 和 1080p）建立就失敗。
- 2.0 的素材有擬真人臉時，GMI 曾在建立請求時直接回 HTTP 500（訊息只說是暫時的後端錯誤，2026-06 觀察到）。
- 2.0 建立請求時可能會同步檢查素材網址，網址打不開時有時直接回 500「Backend error (400)」，有時照樣建立、
  約 10 分鐘後才以「Failed to download media」失敗（同一個請求兩種結果都出現過）。

MiniMax-H3（MiniMax H3）：首尾幀叫 first_frame_image／last_frame_image（送字串，和 GMI 上的 Hailuo 一樣），
參考素材和 Seedance 一樣叫 reference_images／videos／audios（陣列）；一律產生音軌、沒有音軌開關和 seed。
解析度是 768P／2K（大寫）。
"""
import re
import time
from urllib.parse import quote

import requests

from mixroute_video import FAILED, PENDING, check_http

BASE_URL = "https://console.gmicloud.ai/api/v1/ie/requestqueue/apikey"
MODEL = "wan3.0-video"  # 沒指定模型時用這個（加入模型切換之前的任務紀錄都是它）

# 各模型的 payload 格式：media 是 mixroute_video 的 media type → GMI 欄位；single 裡的欄位送字串、其餘送陣列
# （wan3.0-video 和 GMI 網頁後台一樣一律送陣列）；audio 是音軌開關的欄位名稱，None＝一律產生、不送
SEEDANCE = {
    "media": {"first_frame": "first_frame", "last_frame": "last_frame", "reference_image": "reference_images",
              "reference_video": "reference_videos", "reference_audio": "reference_audios"},
    "single": ("first_frame", "last_frame"),
    "audio": "generate_audio",
}
MODELS = {
    "wan3.0-video": {
        "media": {"first_frame": "first_frame", "last_frame": "last_frame", "reference_image": "reference_image",
                  "reference_video": "reference_video", "reference_audio": "audio_url"},
        "single": (),
        "audio": None,
    },
    "seedance-2-0-260128": SEEDANCE,
    "seedance-2-5-260628": SEEDANCE,
    "MiniMax-H3": {
        "media": {**SEEDANCE["media"], "first_frame": "first_frame_image", "last_frame": "last_frame_image"},
        "single": ("first_frame_image", "last_frame_image"),
        "audio": None,
    },
}

# 公告價（美元／秒，失敗不收費）；驗證 key 時會用模型說明裡的 pricing_details 更新。
# Seedance 2.5 的 pricing_details 是空的，只有 price_info 231000（＝$0.231／秒，和第三方報的 720p 價格一致），
# 480p 的價格 GMI 沒有公開。MiniMax-H3 先用 MiniMax 官方的價格
PRICES = {
    "wan3.0-video": {"480P": 0.05, "720P": 0.10, "1080P": 0.20},
    "seedance-2-0-260128": {"480p": 0.07, "720p": 0.152, "1080p": 0.374},
    "seedance-2-5-260628": {"720p": 0.231},
    "MiniMax-H3": {"768P": 0.08, "2K": 0.13},
}

# 本機副檔名 → (上傳 API 的 file_type, PUT 時的 Content-Type)。預簽名網址有綁 Content-Type，
# 兩者要對上：file_type 用 jpg 時 GMI 簽的是非標準的 image/jpg，所以 JPEG 一律用 jpeg。
# 上傳 API 不收 .mov；MOV 和 MP4 是同一種容器格式，以 mp4 上傳。
UPLOAD_TYPES = {
    "jpg": ("jpeg", "image/jpeg"), "jpeg": ("jpeg", "image/jpeg"), "png": ("png", "image/png"),
    "mp4": ("mp4", "video/mp4"), "mov": ("mp4", "video/mp4"),
    "mp3": ("mp3", "audio/mpeg"), "wav": ("wav", "audio/wav"),
}

# GMI 的狀態換成 mixroute_video 的大寫名稱，任務紀錄和網頁才能共用同一套判斷
STATUS = {
    "created": "QUEUED", "queued": "QUEUED", "dispatched": "QUEUED", "processing": "IN_PROGRESS",
    "success": "SUCCESS", "failed": "FAILED", "cancelled": "CANCELLED", "canceled": "CANCELLED",
}


def parse_prices(info):
    """從模型說明的 pricing_details 取出每秒價格，兩種寫法都認得：
    "480P: $0.05/second; 720P: …"（wan3.0-video）和 "Per second: 480p=$0.07, 720p=$0.152"（Seedance 2.0）；
    解析度也可以是 2K、4K 這種寫法。"""
    text = str(info.get("pricing_details") or "")
    return {res: float(price) for res, price in re.findall(r"\b(\d{3,4}[Pp]|\d[Kk])\s*[:=]\s*\$\s*([\d.]+)", text)}


def upload(session, path):
    """把本機檔案傳到 GMI 的儲存空間，回傳公開網址（拿到網址的人都能下載）。"""
    ext = path.suffix[1:].lower()
    if ext not in UPLOAD_TYPES:
        raise ValueError(f"GMI 不接受 .{ext} 檔")
    file_type, mime = UPLOAD_TYPES[ext]
    resp = session.post(f"{BASE_URL}/upload-url", json={"file_type": file_type}, timeout=30)
    check_http(resp)
    info = resp.json()
    if not info.get("upload_url") or not info.get("public_url"):
        raise RuntimeError(f"GMI 沒有給上傳網址：{info}")
    # 預簽名網址本身就有授權，用不帶 API key 的 requests.put，免得把 key 送到儲存空間
    with open(path, "rb") as f:
        put = requests.put(info["upload_url"], data=f, headers={"Content-Type": mime}, timeout=900)
    if not put.ok:
        code = re.search(r"<Code>(.*?)</Code>", put.text)  # 儲存空間（GCS）的錯誤是 XML
        raise RuntimeError(f"上傳到 GMI 失敗：HTTP {put.status_code} {code.group(1) if code else put.text[:200]}")
    return info["public_url"]


def build_payload(model, prompt, parameters, media=None, negative_prompt=""):
    """parameters 和 media 用 mixroute_video 的格式，轉成 GMI 這個模型的 payload。"""
    fmt = MODELS.get(model)
    if not fmt:
        raise ValueError(f"不支援 GMI 的 {model} 模型")
    payload = {"prompt": prompt or ""}
    if negative_prompt:
        payload["negative_prompt"] = negative_prompt
    for k, v in parameters.items():
        if k != "audio":
            payload[k] = v
        elif fmt["audio"]:
            payload[fmt["audio"]] = v
    for m in media or []:
        field = fmt["media"].get(m["type"])
        if not field:
            raise ValueError(f"GMI 的 {model} 不支援 {m['type']} 素材")
        if field in fmt["single"]:
            payload[field] = m["url"]
        else:
            payload.setdefault(field, []).append(m["url"])
    return payload


def create_task(session, prompt, parameters, media=None, negative_prompt="", model=MODEL):
    """parameters 和 media 用 mixroute_video 的格式，回傳 request_id。"""
    body = {"model": model, "payload": build_payload(model, prompt, parameters, media, negative_prompt)}
    resp = session.post(f"{BASE_URL}/requests", json=body, timeout=120)
    check_http(resp)
    result = resp.json()
    request_id = result.get("request_id")
    if not request_id:
        raise RuntimeError(f"建立請求失敗：{result}")
    return request_id


def find_request(session, request_id, model=MODEL, pages=5):
    """GMI 網頁後台建立的請求用 ID 查不到（404），只好從請求列表裡找；列表要指定模型，
    先找 model，找不到再找其他模型（用 ID 查詢時不一定選對模型）。"""
    for model_id in [model, *(m for m in MODELS if m != model)]:
        for page in range(pages):
            resp = session.get(f"{BASE_URL}/requests", params={"model_id": model_id, "limit": 100, "offset": page * 100}, timeout=30)
            check_http(resp)
            data = resp.json()
            for r in data.get("requests") or []:
                if r.get("request_id") == request_id:
                    return r
            if not data.get("has_more"):
                break
    return None


def video_url(task):
    outcome = task.get("outcome") or {}
    for m in outcome.get("media_urls") or []:
        if m.get("url"):
            return m["url"]
    return outcome.get("video_url") or ""


def failure_reason(task):
    """失敗原因。outcome.error 可能是字串，也可能是 {"code", "message", "status"}（Seedance）。"""
    err = (task.get("outcome") or {}).get("error") or task.get("error")
    if isinstance(err, dict):
        msg, status = err.get("message"), err.get("status")
        if msg:
            return f"{msg}（{status}）" if status else msg
    return err or task


def wait_for_task(session, request_id, timeout=1200, interval=15, on_update=None, model=MODEL):
    """約每 15 秒查詢一次，直到成功、失敗或逾時，回傳 GMI 的請求物件（影片網址用 video_url() 取）。

    有給 on_update(status, task, elapsed) 時每次查詢都會呼叫，status 已換成 mixroute_video 的名稱。
    """
    url = f"{BASE_URL}/requests/{quote(request_id, safe='')}"
    start = time.monotonic()
    deadline = start + timeout
    delay = interval
    while time.monotonic() < deadline:
        try:
            resp = session.get(url, timeout=30)
            task = find_request(session, request_id, model) if resp.status_code == 404 else None
        except (requests.Timeout, requests.ConnectionError) as e:
            print(f"  連線問題，稍後重試：{e}", flush=True)
            delay = min(delay * 2, 60)
        else:
            if resp.status_code in (429, 500, 502, 503, 504):
                print(f"  HTTP {resp.status_code}，稍後重試", flush=True)
                delay = min(delay * 2, 60)
            else:
                if task is None:
                    check_http(resp)
                    task = resp.json()
                raw = str(task.get("status", "")).lower()
                status = STATUS.get(raw, raw.upper())
                if on_update:
                    on_update(status, task, time.monotonic() - start)
                if status == "SUCCESS":
                    return task
                if status in FAILED:
                    raise RuntimeError(f"生成失敗：{failure_reason(task)}")
                if status not in PENDING:
                    raise RuntimeError(f"未知的請求狀態 {raw!r}：{task}")
                delay = interval
        time.sleep(max(0, min(delay, deadline - time.monotonic())))
    raise TimeoutError(f"請求 {request_id} 仍未完成")
