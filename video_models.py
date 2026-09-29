"""各 API 能用的影片模型，以及每個模型的參數範圍與素材限制。

網頁（video_ui.html）依這份資料畫出左邊的表單並即時檢查；伺服器（video_ui.py）送出前用同一份資料再檢查一次。
新增模型：在 MODELS 加一筆；payload 格式不同的話，再到對應的 API 模組（mixroute_video.py／gmi_video.py）處理。

欄位：
- resolutions／ratios：可選的值，照 API 要的大小寫；defaults 是「恢復預設」用的值。
- text_adaptive：純文字生影片（沒有任何素材）能不能用自適應比例（False＝一定要指定比例，這時改用 defaults 的比例）。
- duration：秒數範圍；auto 為真時可以送 -1（由模型決定長度）。seed：範圍；random 為真時可以送 -1；None＝不能指定 seed。
- audio："toggle" 可選要不要產生音軌，"always" 一律產生。options：其他開關
  （prompt_extend 提示詞擴寫、watermark 浮水印、web_search 聯網搜尋）。
- prompt_max：提示詞字數上限（None＝文件沒寫）；negative_max：負面提示詞上限（0＝沒有這個欄位）。
- media：各種素材最多幾個，沒列的就是不支援；media_total：素材總數上限。
- clip／clip_sum：參考影片、音訊每段的秒數範圍，以及合計上限。
- ref_video_plus_output：參考影片合計＋生成時長的上限（Wan 3.0 的規定），None＝沒有。
- audio_alone：參考音訊能不能單獨使用（False＝要搭配至少一張參考圖片或一段參考影片）。
- real_faces：素材裡能不能有擬真的人臉（Seedance 不行，真人照片和 AI 生成的都一樣）。
- image／video：素材的格式、尺寸限制（max_mb：每個檔案的大小上限）。image.formats 是本機圖片能用的格式（GMI 的上傳 API 只收 JPEG／PNG）。
- labels：提示詞裡指稱素材的寫法（图1、@Image1、Image 1…），後面直接接編號。
- file_label：檔名裡的模型名稱（檔名是「日期_時間_模型_名稱」，見 video_ui.py 的 base_stem），不能有空白和檔名不能用的字元。
- frame_ratio：首尾幀模式的比例，"suggest" 建議用自適應，"force" 一定是自適應。
- video_edit：能不能做影片編輯（編輯要時長 -1 的模型，在不支援 -1 的 API 上會失敗）。
- notes：顯示在各區塊說明後面的提醒（image／video／audio／frame），price 是有參考影片時接在預估費用後面的說明。
"""

WAN_RATIOS = ["adaptive", "16:9", "4:3", "1:1", "3:4", "9:16"]
WAN_MEDIA = {"reference_image": 10, "reference_video": 5, "reference_audio": 5, "first_frame": 1, "last_frame": 1}
WAN_CLIP = {"reference_video": [1, 15], "reference_audio": [1, 15]}
WAN_CLIP_SUM = {"reference_video": 15, "reference_audio": 15}
WAN_LABELS = {"image": "图", "video": "视频", "audio": "音频"}  # 官方文件的指稱方式
WAN_VIDEO = {"min_side": 240, "max_side": 4096, "max_ratio": 8}

# 文件：https://docs.mixroute.ai/en/model-api/alibaba/wan3.0-video
MIXROUTE_WAN = {
    "provider": "mixroute", "id": "wan3.0-video", "label": "Wan 3.0", "file_label": "Wan3.0",
    "prompt_max": 20000, "negative_max": 0, "prompt_required": False,
    "resolutions": ["480P", "720P", "1080P"], "ratios": WAN_RATIOS, "text_adaptive": True,
    "defaults": {"resolution": "480P", "ratio": "16:9", "duration": 2, "audio": False},
    "duration": {"min": 2, "max": 30, "auto": True},
    "seed": {"min": 0, "max": 2147483647, "random": True},
    "audio": "toggle", "options": ["prompt_extend", "watermark"],
    "media": {**WAN_MEDIA, "file": 1, "link": 1}, "media_total": 20,
    "clip": WAN_CLIP, "clip_sum": WAN_CLIP_SUM, "ref_video_plus_output": 30,
    "audio_alone": True, "real_faces": True,
    "image": {"formats": ["jpg", "png", "webp", "bmp"], "min_side": 240, "max_side": 8000, "max_ratio": 8, "max_mb": 20},
    "video": WAN_VIDEO,
    "labels": WAN_LABELS, "frame_ratio": "suggest", "video_edit": True,
    "notes": {},
}

# 模型說明：GET https://console.gmicloud.ai/api/v1/ie/requestqueue/apikey/models/wan3.0-video
GMI_WAN = {
    **MIXROUTE_WAN,
    "provider": "gmi",
    "prompt_max": 5000, "negative_max": 500,
    "duration": {"min": 2, "max": 30, "auto": False},
    "seed": {"min": 0, "max": 2147483647, "random": False},
    "audio": "always",
    "media": WAN_MEDIA,
    "image": {**MIXROUTE_WAN["image"], "formats": ["jpg", "png"]},
}

# Seedance 2.0／2.5 共用的素材尺寸限制（BytePlus 建立任務 API：https://docs.byteplus.com/en/docs/ModelArk/1520757）
SEEDANCE_IMAGE = {"formats": ["jpg", "png"], "min_side": 300, "max_side": 6000, "max_ratio": 2.5, "max_mb": 30}
SEEDANCE_VIDEO = {"min_side": 300, "max_side": 6000, "max_ratio": 2.5, "min_pixels": 407696, "max_pixels": 8295044}

# BytePlus Seedance 2.0：https://docs.byteplus.com/en/docs/ModelArk/2291680
# GMI 文件：https://docs.gmicloud.ai/model-quickstarts/video/seedance-2-0-260128
# 和 2.5 的差異：時長 4–15 秒；參考影片、音訊每段 2–15 秒、各自合計 ≤ 15 秒；有 1080p；首尾幀可以指定比例；
# 參考音訊不能單獨用。2026-09 經 GMI 實測：文件說提示詞可省略，但空的提示詞會失敗（content must include at least
# one text item）；時長 -1 預扣費用失敗；4k 在模型說明的選項裡有，但沒有價格，GMI 文件也只列 480p／720p／1080p，所以不放。
GMI_SEEDANCE_20 = {
    "provider": "gmi", "id": "seedance-2-0-260128", "label": "Seedance 2.0", "file_label": "Seedance2.0",
    "prompt_max": None, "negative_max": 0, "prompt_required": True,
    "resolutions": ["480p", "720p", "1080p"],
    "ratios": ["adaptive", "16:9", "4:3", "1:1", "3:4", "9:16", "21:9"], "text_adaptive": True,
    "defaults": {"resolution": "480p", "ratio": "16:9", "duration": 5, "audio": True},
    "duration": {"min": 4, "max": 15, "auto": False},
    "seed": {"min": 0, "max": 2147483647, "random": True},
    "audio": "toggle", "options": ["watermark", "web_search"],
    "media": {"reference_image": 9, "reference_video": 3, "reference_audio": 3, "first_frame": 1, "last_frame": 1},
    "media_total": 15,
    "clip": {"reference_video": [2, 15], "reference_audio": [2, 15]},
    "clip_sum": {"reference_video": 15, "reference_audio": 15},
    "ref_video_plus_output": None,
    "audio_alone": False, "real_faces": False,
    "image": SEEDANCE_IMAGE,
    "video": SEEDANCE_VIDEO,
    "labels": {"image": "Image ", "video": "Video ", "audio": "Audio "},  # 官方寫法：Image 1、Video 1、Audio 1
    "frame_ratio": "suggest", "video_edit": True,
    "notes": {
        "image": "Seedance 不接受有擬真人臉的素材（真人照片或 AI 生成的都一樣），會被拒絕（失敗不收費）。",
        "video": "影片要 24–60 fps。",
        "audio": "Seedance 2.0 不能只給音訊，要搭配至少一張參考圖片或一段參考影片。",
        "frame": "Seedance 2.0 的首尾幀可以指定比例，但和首幀比例不同時畫面會被置中裁切；尾幀比例和首幀不同時，尾幀會被裁切成首幀的比例。",
    },
}

# BytePlus Seedance 2.5：https://docs.byteplus.com/en/docs/ModelArk/2607688
# 經 GMI 呼叫時以 GMI 的限制為準（2026-09 實測）：參考圖最多 9 張（多送回 400）、影片和音訊各 3 段；
# 只有 480p／720p（1080p 回「找不到價格」）；時長不能送 -1（建立請求時預扣費用會失敗）。
GMI_SEEDANCE_25 = {
    "provider": "gmi", "id": "seedance-2-5-260628", "label": "Seedance 2.5", "file_label": "Seedance2.5",
    "prompt_max": None, "negative_max": 0, "prompt_required": True,
    "resolutions": ["480p", "720p"],
    "ratios": ["adaptive", "16:9", "4:3", "1:1", "3:4", "9:16", "21:9"], "text_adaptive": True,
    "defaults": {"resolution": "480p", "ratio": "16:9", "duration": 5, "audio": True},
    "duration": {"min": 4, "max": 30, "auto": False},
    "seed": {"min": 0, "max": 4294967295, "random": False},
    "audio": "toggle", "options": ["watermark", "web_search"],
    "media": {"reference_image": 9, "reference_video": 3, "reference_audio": 3, "first_frame": 1, "last_frame": 1},
    "media_total": 15,
    "clip": {"reference_video": [2, 30], "reference_audio": [2, 30]},
    "clip_sum": {"reference_video": 30, "reference_audio": 30},
    "ref_video_plus_output": None,
    "audio_alone": True, "real_faces": False,
    "image": SEEDANCE_IMAGE,
    "video": SEEDANCE_VIDEO,
    "labels": {"image": "@Image", "video": "@Video", "audio": "@Audio"},
    "frame_ratio": "force", "video_edit": False,
    "notes": {
        "image": "Seedance 不接受有擬真人臉的素材（真人照片或 AI 生成的都一樣），會被拒絕（失敗不收費）。",
        "video": "可以做影片延長（比例要自適應）；影片編輯官方要求時長 -1，GMI 不支援，編輯任務會失敗。",
        "frame": "Seedance 的首尾幀模式比例固定是自適應，輸出會跟首幀一致；尾幀比例和首幀不同時會被拉伸。",
        "price": "有參考影片時 GMI 另外計價，實際費用會比這個高",
    },
}

# MiniMax H3：https://platform.minimax.io/docs/api-reference/video-generation-v2-create
# GMI 文件（https://docs.gmicloud.ai/model-quickstarts/video/minimax-h3）只列欄位名稱，範圍照 MiniMax 官方文件。
# 和 Seedance 的差異：768P／2K；一律產生音軌（原生立體聲），沒有 seed、浮水印等開關；純文字生影片一定要指定比例
# （不能自適應），首尾幀模式的比例固定自適應（送別的也會被當成自適應）；素材合計最多 12 個；影片 ≤ 50 MB、23.976–60 fps。
GMI_MINIMAX_H3 = {
    "provider": "gmi", "id": "MiniMax-H3", "label": "MiniMax H3", "file_label": "MiniMaxH3",
    "prompt_max": 7000, "negative_max": 0, "prompt_required": True,
    "resolutions": ["768P", "2K"],
    "ratios": ["adaptive", "16:9", "4:3", "1:1", "3:4", "9:16", "21:9"], "text_adaptive": False,
    "defaults": {"resolution": "768P", "ratio": "16:9", "duration": 5, "audio": True},
    "duration": {"min": 4, "max": 15, "auto": False},
    "seed": None,
    "audio": "always", "options": [],
    "media": {"reference_image": 9, "reference_video": 3, "reference_audio": 3, "first_frame": 1, "last_frame": 1},
    "media_total": 12,
    "clip": {"reference_video": [2, 15], "reference_audio": [2, 15]},
    "clip_sum": {"reference_video": 15, "reference_audio": 15},
    "ref_video_plus_output": None,
    "audio_alone": False, "real_faces": True,
    "image": {"formats": ["jpg", "png"], "min_side": 256, "max_side": 5760, "max_ratio": 2.5, "max_mb": 30},
    "video": {"min_side": 256, "max_side": 5760, "max_ratio": 2.5, "max_mb": 50},
    "labels": {"image": "Image ", "video": "Video ", "audio": "Audio "},  # 官方寫法：Image 1、Video 1、Audio 1
    "frame_ratio": "force", "video_edit": True,
    "notes": {
        "image": "圖片、影片、音訊合計最多 12 個。",
        "video": "影片要 H.264／H.265 編碼、24–60 fps。",
        "audio": "MiniMax H3 不能只給音訊，要搭配至少一張參考圖片或一段參考影片；可以拿來指定說話的音色或背景音樂。",
        "price": "參考影片的秒數按同一個單價另外計費，實際費用會比這個高",
    },
}

MODELS = [MIXROUTE_WAN, GMI_WAN, GMI_SEEDANCE_20, GMI_SEEDANCE_25, GMI_MINIMAX_H3]  # 網頁的模型選單照這個順序
