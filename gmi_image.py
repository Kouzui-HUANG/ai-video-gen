"""GMI Cloud 的圖片生成（request queue API）：GPT Image 2.5（Sunburst、Flare）、GPT Image 2、Gemini 3 Pro Image
和 Seedream 5.0 Pro。

模型說明：GET {BASE_URL}/models/<model>（公開文件站 2026-09 還沒有 2.5，參數和
https://docs.gmicloud.ai/model-quickstarts/image/gpt-image-2-edit 同一套；Gemini 見
https://docs.gmicloud.ai/model-quickstarts/image/gemini-3-pro-image）。
給 video_ui.py 用；各模型的參數範圍與價格在 image_models.py。查詢狀態沿用 gmi_video 的 wait_for_task。

- GPT Image 分成 -generate（文字生圖）和 -edit（參考圖編輯）；edit 的 image 可以是網址、base64 data URI，或最多 16 個的陣列。
- Gemini 3 Pro Image 只有一個 ID，image（最多 14 個網址的陣列）是選填；尺寸只送 aspect_ratio 和 image_size，
  輸出格式叫 image_output_format。payload 一樣是 prompt ＋ 參數 ＋ image，回應一樣是 outcome.media_urls。
- Seedream 5.0 Pro 也只有一個 ID，參數是 size（寬x高）、output_format、watermark。它是非同步模型：
  POST /requests 馬上回傳 request_id（status queued），create() 照樣回傳，由呼叫的一方用 gmi_video.wait_for_task 查到完成。
- GPT Image 2 的錯誤訊息比較具體（例如「size dimensions must be multiples of 16」「failed to fetch image」），
  2.5 的錯誤一律是下面那句 Generation rejected。
- 同步模型（模型說明的 delivery_mode 是 sync）：POST /requests 要等圖片生成完才回應，成功時回傳的請求物件裡
  直接有 outcome.media_urls；失敗時回 HTTP 400 {"error", "request_id"}，請求紀錄是 status failed、
  outcome.error {code, message, status}。2026-09 實測：參考圖網址打不開時約 3 秒就回 400
  「Generation rejected; please review the prompt and parameters then retry」（status INVALID_INPUT）。
- 送出後逾時或連線中斷時，請求可能已經建立而且扣款了，不能重送：用 find_by_payload() 從請求列表找回。
- 計價：建立請求時預扣，預扣的金額就是最終價格；quality 送 auto 或不送會按 max 計價，所以一定要送明確的品質。
"""
import os
import re

import requests

from gmi_video import BASE_URL, STATUS, failure_reason
from mixroute_video import FAILED, check_http


class RequestFailed(RuntimeError):
    """GMI 回報這個請求失敗了；request_id 是 GMI 留下的請求紀錄（有的話）。"""

    def __init__(self, message, request_id=None):
        super().__init__(message)
        self.request_id = request_id


class LostResponse(RuntimeError):
    """送出後沒拿到結果（逾時、連線中斷、閘道錯誤頁）：請求可能已經建立，要從請求列表找回，不能重送。"""


def parse_prices(info):
    """按像素數計價的模型（GPT Image 2.5）：從 pricing_details 取出 1024×1024 每張的價格：「low $0.0059, medium $0.0132, …」。"""
    text = str(info.get("pricing_details") or "")
    return {q: float(p) for q, p in re.findall(r"\b(low|medium|high|xhigh|max)\s+\$\s*(\d+(?:\.\d+)?)", text)}


def parse_size_prices(info):
    """按尺寸計價的模型（GPT Image 2）：「low 1024x1024=$0.010, low 1024x1536=$0.020; …」→
    {"1024x1536": {"low": 0.02, …}, …}，寬高小的在前（1536x1024 和 1024x1536 同價）。"""
    text = str(info.get("pricing_details") or "")
    prices = {}
    for q, w, h, p in re.findall(r"\b(low|medium|high|xhigh|max)\s+(\d+)x(\d+)\s*=\s*\$\s*(\d+(?:\.\d+)?)", text):
        w, h = int(w), int(h)
        prices.setdefault(f"{min(w, h)}x{max(w, h)}", {})[q] = float(p)
    return prices


def parse_tier_prices(info):
    """按解析度計價的模型（Gemini 3 Pro Image）：「For output, $0.134 per 1K/2K image and $0.24 per 4K image」→
    {"1K": 0.134, "2K": 0.134, "4K": 0.24}。前面「For input, $0.0011 per image」是每張參考圖的價格，不在這裡。"""
    text = str(info.get("pricing_details") or "")
    prices = {}
    for price, tiers in re.findall(r"\$\s*(\d+(?:\.\d+)?)\s*per\s+(\d+K(?:\s*/\s*\d+K)*)\s+image", text, re.I):
        for tier in re.split(r"\s*/\s*", tiers):
            prices[tier.upper()] = float(price)
    return prices


def parse_flat_price(info):
    """不分尺寸、每張同價的模型（Seedream 5.0 Pro）：「$0.085 per image」→ {"image": 0.085}。"""
    m = re.search(r"\$\s*(\d+(?:\.\d+)?)\s*per\s+image", str(info.get("pricing_details") or ""), re.I)
    return {"image": float(m.group(1))} if m else {}


def build_payload(prompt, parameters, images=()):
    """parameters 是 video_ui 檢查過的 size、quality、n…；有參考圖時加上 image（一律送陣列）。"""
    payload = {"prompt": prompt, **parameters}
    if images:
        payload["image"] = list(images)
    return payload


def create(session, model, payload, timeout=900):
    """送出請求並等它生成完，回傳 GMI 的請求物件（request_id、status、outcome）。

    GMI 回報失敗時拋出 RequestFailed；沒拿到結果時拋出 LostResponse（這時不要重送）。
    """
    try:
        resp = session.post(f"{BASE_URL}/requests", json={"model": model, "payload": payload}, timeout=(30, timeout))
    except requests.RequestException as e:  # 包括收到一半斷線（ChunkedEncodingError），這時請求多半已經建立
        what = "逾時" if isinstance(e, requests.Timeout) else "連線中斷"
        raise LostResponse(f"等 GMI 回應時{what}") from None
    try:
        data = resp.json()
    except ValueError:
        data = None
    if not isinstance(data, dict):
        if resp.status_code >= 500:  # 閘道回的錯誤頁：上游可能還在生成
            raise LostResponse(f"GMI 回傳 HTTP {resp.status_code} 錯誤頁")
        check_http(resp)
        raise RuntimeError(f"GMI 回傳的不是 JSON：{resp.text[:300]}")
    if not resp.ok:
        err = data.get("error")
        msg = (err.get("message") if isinstance(err, dict) else err) or data.get("message") or resp.text[:300]
        raise RequestFailed(f"HTTP {resp.status_code}：{msg}", data.get("request_id"))
    if STATUS.get(str(data.get("status", "")).lower()) in FAILED:
        raise RequestFailed(str(failure_reason(data)), data.get("request_id"))
    if not data.get("request_id"):
        raise RuntimeError(f"建立請求失敗：{str(data)[:300]}")
    return data


def find_by_payload(session, model, payload, since, exclude=(), pages=2):
    """從請求列表找出 since（秒）之後建立、payload 完全相同的請求；沒拿到 request_id 時用來找回。

    送出時就被擋下的請求（例如 Seedream 回 HTTP 500「Backend error (400)」）沒給 request_id，卻會以 failed 留在列表裡，
    所以先找沒失敗的：多張的任務裡有一張被擋、另一張斷線時，斷線的那張才會找回自己的請求。都沒有才用失敗的。"""
    failed = None
    for page in range(pages):
        resp = session.get(f"{BASE_URL}/requests", params={"model_id": model, "limit": 100, "offset": page * 100}, timeout=30)
        check_http(resp)
        data = resp.json()
        for r in data.get("requests") or []:
            if r.get("request_id") not in exclude and (r.get("created_at") or 0) >= since - 60 and r.get("payload") == payload:
                if str(r.get("status", "")).lower() != "failed":
                    return r
                failed = failed or r
        if not data.get("has_more"):
            break
    return failed


def image_urls(task):
    """生成的圖片網址，照 GMI 回傳的順序。"""
    urls = []
    for m in (task.get("outcome") or {}).get("media_urls") or []:
        url = m.get("url") if isinstance(m, dict) else m
        if isinstance(url, str) and url:
            urls.append(url)
    return urls


def sniff(head):
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def download(url, folder, stem, fmt=None, finish=None):
    """下載一張圖片存成 folder/<stem>.<副檔名>，副檔名看檔案內容（認不出來才用 output_format），回傳路徑。

    圖片網址本身就能下載，不帶 API key；先寫到 .part 再改名，中途失敗不會留下看似完整的檔案。
    finish(.part 的路徑) 在改名前處理檔案（video_ui.py 寫入生成設定）。
    """
    folder.mkdir(parents=True, exist_ok=True)
    part = folder / f"{stem}.part"
    with requests.get(url, stream=True, timeout=120) as resp:
        check_http(resp)
        with open(part, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    with open(part, "rb") as f:
        ext = sniff(f.read(12)) or {"jpeg": "jpg"}.get(fmt, fmt) or "png"
    path = folder / f"{stem}.{ext}"
    if finish:
        finish(part)
    os.replace(part, path)
    return path
