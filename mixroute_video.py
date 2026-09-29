#!/usr/bin/env python3
"""MixRoute Wan 3.0 影片生成：建立任務 → 輪詢狀態 → 下載 MP4。

文件：https://docs.mixroute.ai/en/model-api/alibaba/wan3.0-video

用法（需要 `pip install requests`）：
    export MIXROUTE_API_KEY="sk-..."
    python3 mixroute_video.py "一隻橘貓在窗台上伸懶腰"
    python3 mixroute_video.py "海浪拍打礁岩，空拍鏡頭" --resolution 720P --ratio 9:16 --duration 5 --audio
    python3 mixroute_video.py --task-id <task_id>   # 接續查詢已送出的任務，不會重新建立
"""
import argparse
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote, urlparse

import requests

BASE_URL = "https://api.mixroute.ai/v1"
MODEL = "wan3.0-video"

PENDING = {"QUEUED", "NOT_START", "PENDING", "SUBMITTED", "IN_PROGRESS", "RUNNING"}
FAILED = {"FAILURE", "FAILED", "EXPIRED", "CANCELED", "CANCELLED", "UNKNOWN"}
OK_CODES = (None, 0, 200, "0", "200", "success")


def check_http(resp):
    """HTTP 錯誤時連同回應內容一起拋出，才看得到 key 錯誤、額度不足等訊息。"""
    if not resp.ok:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:1000]}")


def build_payload(prompt, parameters, media=None):
    """media 是 [{"type": "reference_image", "url": "..."}, ...]；有素材時 prompt 可省略。"""
    task_input = {}
    if prompt:
        task_input["prompt"] = prompt
    if media:
        task_input["media"] = media
    return {
        "model": MODEL,
        "metadata": {"input": task_input, "parameters": parameters},
    }


def create_task(session, prompt, parameters, media=None):
    resp = session.post(f"{BASE_URL}/video/generations", json=build_payload(prompt, parameters, media), timeout=120)
    check_http(resp)
    result = resp.json()
    task_id = result.get("task_id") or result.get("id")
    if not task_id:
        raise RuntimeError(f"建立任務失敗：{result}")
    return task_id


def wait_for_task(session, task_id, timeout=1200, interval=15, on_update=None):
    """約每 15 秒查詢一次，直到 SUCCESS / FAILURE 或逾時，回傳回應中的 data 物件。

    有給 on_update(status, task, elapsed) 時改呼叫它，不印進度（網頁介面用）。
    """
    url = f"{BASE_URL}/video/generations/{quote(task_id, safe='')}"
    start = time.monotonic()
    deadline = start + timeout
    delay = interval
    while time.monotonic() < deadline:
        try:
            resp = session.get(url, timeout=30)
        except (requests.Timeout, requests.ConnectionError) as e:
            print(f"  連線問題，稍後重試：{e}", flush=True)
            delay = min(delay * 2, 60)
        else:
            if resp.status_code in (429, 500, 502, 503, 504):
                print(f"  HTTP {resp.status_code}，稍後重試", flush=True)
                delay = min(delay * 2, 60)
            else:
                check_http(resp)
                result = resp.json()
                # code="success" 只代表查詢成功，生成是否成功要看 data.status
                if result.get("code") not in OK_CODES:
                    raise RuntimeError(f"查詢失敗：{result}")
                task = result.get("data") or {}
                status = str(task.get("status", "")).upper()
                elapsed = time.monotonic() - start
                if on_update:
                    on_update(status, task, elapsed)
                else:
                    print(f"  [{elapsed:4.0f}s] status={status} progress={task.get('progress') or '-'}", flush=True)
                if status == "SUCCESS":
                    return task
                if status in FAILED:
                    # 失敗時 result_url 可能放的是錯誤文字，不是網址
                    reason = task.get("fail_reason") or task.get("result_url") or task
                    raise RuntimeError(f"生成失敗：{reason}")
                if status not in PENDING:
                    raise RuntimeError(f"未知的任務狀態 {status!r}：{result}")
                delay = interval
        time.sleep(max(0, min(delay, deadline - time.monotonic())))
    raise TimeoutError(f"任務仍未完成，稍後可用 --task-id {task_id} 接續查詢")


def download(url, path, finish=None):
    # 影片網址是簽名連結，不帶 API key 直接下載，避免把 key 送到第三方主機
    # 先寫到 .part 再改名，中途失敗不會留下看似完整的檔案；finish(.part 的路徑) 在改名前處理檔案（video_ui.py 寫入生成設定）
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    with requests.get(url, stream=True, timeout=120) as resp:
        check_http(resp)
        with open(part, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    if finish:
        finish(part)
    os.replace(part, path)
    return path


def main():
    p = argparse.ArgumentParser(description="MixRoute Wan 3.0 文字生成影片")
    p.add_argument("prompt", nargs="?", help="影片描述，中英文皆可")
    p.add_argument("--resolution", default="480P", choices=["480P", "720P", "1080P"])
    p.add_argument("--ratio", default="16:9", choices=["adaptive", "16:9", "4:3", "1:1", "3:4", "9:16"])
    p.add_argument("--duration", type=int, default=2, help="秒數 2-30，或 -1 由模型決定（預設 2）")
    p.add_argument("--audio", action="store_true", help="產生音軌（預設無聲）")
    p.add_argument("--prompt-extend", action="store_true", help="讓模型自動擴寫提示詞")
    p.add_argument("--watermark", action="store_true", help="加上 AI 浮水印")
    p.add_argument("--seed", type=int, help="隨機種子 0-2147483647")
    p.add_argument("--task-id", help="不建立新任務，直接查詢這個既有任務")
    p.add_argument("--output", type=Path, help="輸出路徑（預設 outputs/<task_id>.mp4）")
    p.add_argument("--timeout", type=int, default=1200, help="最長等待秒數（預設 1200）")
    args = p.parse_args()

    if not args.prompt and not args.task_id:
        p.error("請提供 prompt，或用 --task-id 查詢既有任務")
    if not (args.duration == -1 or 2 <= args.duration <= 30):
        p.error("--duration 必須是 2-30 或 -1")
    api_key = os.environ.get("MIXROUTE_API_KEY")
    if not api_key:
        p.error("請先設定環境變數 MIXROUTE_API_KEY")

    with requests.Session() as session:
        session.headers["Authorization"] = f"Bearer {api_key}"
        task_id = args.task_id
        if not task_id:
            parameters = {
                "resolution": args.resolution,
                "ratio": args.ratio,
                "duration": args.duration,
                "audio": args.audio,
                "prompt_extend": args.prompt_extend,
                "watermark": args.watermark,
            }
            if args.seed is not None:
                parameters["seed"] = args.seed
            task_id = create_task(session, args.prompt, parameters)
            print(f"任務已建立：task_id={task_id}", flush=True)
        task = wait_for_task(session, task_id, timeout=args.timeout)

    video_url = task.get("result_url", "")
    if urlparse(video_url).scheme not in ("http", "https"):
        raise RuntimeError(f"任務成功但沒有有效的影片網址：{task}")
    out = download(video_url, args.output or Path("outputs") / f"{task_id}.mp4")
    print(f"影片網址：{video_url}")
    print(f"已下載：{out}（{out.stat().st_size / 1024:.0f} KB）")
    usage = (task.get("data") or {}).get("usage")
    if usage:
        print(f"用量：{usage}")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, TimeoutError, requests.RequestException) as e:
        sys.exit(f"錯誤：{e}")
