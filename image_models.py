"""GMI Cloud 上能用的圖片模型（GPT Image 2.5、GPT Image 2、Gemini 3 Pro Image），以及參數範圍與價格。

網頁（video_ui.html）的「圖片」模式依這份資料畫出參數表單、即時檢查和估價；伺服器（video_ui.py）送出前用同一份資料再檢查一次。
模型說明：GET https://console.gmicloud.ai/api/v1/ie/requestqueue/apikey/models/<model>
（不帶 key 的 …/requestqueue/models/<model> 也查得到。公開文件站 2026-09 有 gpt-image-2-edit 和 gemini-3-pro-image，
GPT Image 的價格表已經過時，以模型說明為準）。
新增模型：在 MODELS 加一筆；payload 格式不同的話，再到 gmi_image.py 處理。

GPT Image 在 GMI 上拆成兩個 ID：沒有參考圖時送 generate（文字生圖），有參考圖時送 edit（照提示詞修改或合成參考圖）。
Sunburst 和 Flare 的參數、價格完全相同，差別只在上游的模型（Sunburst 細節和改圖精準度最好，Flare 最快）。
GPT Image 2 是上一代，參數比較少，價格按尺寸分級（見 GPT_IMAGE_2 上面的說明）。
Gemini 3 Pro Image 只有一個 ID，也不能指定寬高，只選比例和解析度（見 GEMINI_3_PRO_IMAGE 上面的說明）。

欄位：
- generate／edit：兩個 GMI 模型 ID（只有一個 ID 的模型兩個一樣）；summary：模型選單的說明。
- media：參考圖最多幾張（edit 的 image 可以送最多 16 張的陣列）；labels：提示詞裡指稱參考圖的寫法，後面直接接編號。
- image：參考圖的格式和大小（OpenAI 沒有限制尺寸，只要 ≤ 50 MB；本機圖片經 GMI 的上傳 API，只能是 JPEG／PNG）。
- sizing：怎麼指定輸出尺寸。"pixels"：送 size（寬x高），網頁可以選比例＋解析度或自訂寬高；
  "ratio"：送 aspect_ratio（ratios 其中之一）和 image_size（tiers 其中之一），實際尺寸由模型決定。
- size：sizing 是 pixels 時的尺寸規則：寬高都是 multiple 的倍數、每邊 ≤ max_side、長寬比 ≤ max_ratio、
  總像素在 min_pixels–max_pixels。
  ratios、tiers 是網頁上的比例和解析度選項（tiers：pixels＝總像素約多少，long＝長邊多長，超過上限時等比例縮小）；
  tier_sizes：某個解析度＋比例直接用指定的尺寸，不照 tiers 算（GPT Image 2 用來對上有公開價格的尺寸；
  sizing 是 ratio 的模型用來顯示實際會輸出的尺寸）。
- qualities：品質（空的＝沒有這個參數）。auto 不列出來：GMI 對 auto（或不送）一律按最高品質計價。
- extra_params：除了 prompt、image、尺寸、quality、n 以外，generate／edit 各收哪些參數（output_format、output_compression、
  background、moderation）；沒列的不送，網頁上會說明這次用什麼。format_param：輸出格式在 payload 裡的名稱。
- formats：輸出格式；transparent_formats：能輸出透明背景的格式；backgrounds、moderation：可選的值（空的＝不支援）；
  n：一次生成幾張（None＝沒有這個參數，一次一張）；defaults：「恢復預設」和模型不支援使用者的選擇時用的值。
- price_rule、prices：每張的價格（美元）。"pixels"：prices 是 1024×1024 的價格，其他尺寸按像素數等比例換算；
  "sizes"：prices 是「寬x高（小的在前）→ 品質 → 價格」，沒列的尺寸 GMI 接受但沒有公開價格；
  "tiers"：prices 是「解析度 → 價格」。
  GMI 建立請求時預扣費用。驗證 key 時會用模型說明的 pricing_details 更新 prices。
- ref_price：edit 每張參考圖（最多）加收的費用；token_prices：每百萬 token 的價格（text＝提示詞，約 3 bytes 一個 token；
  image＝參考圖；output＝生成的圖），按 token 計價的模型才有。生成完 GMI 會回報實際用量（outcome.request_usage），
  任務列表用它（或 prices）算出實際費用。
"""

SIZE = {"multiple": 16, "max_side": 3840, "max_ratio": 3, "min_pixels": 655360, "max_pixels": 8294400}
ALL_EXTRA_PARAMS = ["output_format", "output_compression", "background", "moderation"]

# 各代共用：參考圖、輸出尺寸的規則和選項、張數
GPT_IMAGE = {
    "kind": "image", "provider": "gmi",
    "prompt_required": True, "prompt_max": None,
    "media": {"reference_image": 16}, "media_total": 16,
    "labels": {"image": "Image "},
    "image": {"formats": ["jpg", "png"], "max_mb": 50},
    "clip": {}, "clip_sum": {},
    "sizing": "pixels", "size": SIZE,
    "ratios": ["1:1", "4:3", "3:4", "3:2", "2:3", "16:9", "9:16", "21:9"],
    "tiers": {"1K": {"pixels": 1024 * 1024}, "2K": {"long": 2048}, "4K": {"long": 3840}},
    "n": {"min": 1, "max": 10},
    "format_param": "output_format",
    "defaults": {"quality": "medium", "n": 1, "output_format": "png", "background": "auto", "moderation": "auto",
                 "output_compression": 100},
    "notes": {},
}

# 2.5 按 token 計價，預扣的金額就是最終價格；quality 送 auto 會按 max 計價
GPT_IMAGE_25 = {
    **GPT_IMAGE,
    "qualities": ["low", "medium", "high", "xhigh", "max"],
    "extra_params": {"generate": ALL_EXTRA_PARAMS, "edit": ALL_EXTRA_PARAMS},
    "formats": ["png", "jpeg", "webp"], "transparent_formats": ["png", "webp"],
    "backgrounds": ["auto", "transparent", "opaque"],
    "moderation": ["auto", "low"],
    "price_rule": "pixels",
    "prices": {"low": 0.0059, "medium": 0.0132, "high": 0.0527, "xhigh": 0.0937, "max": 0.2107},
    "ref_price": 0.012288,
    "token_prices": {"text": 5.0, "image": 8.0, "output": 30.0},
}

GPT_IMAGE_25_SUNBURST = {
    **GPT_IMAGE_25,
    "id": "gpt-image-2.5-sunburst", "label": "GPT Image 2.5 Sunburst",
    "generate": "gpt-image-2.5-sunburst-generate", "edit": "gpt-image-2.5-sunburst-edit",
    "summary": "細節最好、改圖最精準，速度比 Flare 慢",
}

GPT_IMAGE_25_FLARE = {
    **GPT_IMAGE_25,
    "id": "gpt-image-2.5-flare", "label": "GPT Image 2.5 Flare",
    "generate": "gpt-image-2.5-flare-generate", "edit": "gpt-image-2.5-flare-edit",
    "summary": "最快，適合日常生成和打草稿，價格和 Sunburst 相同",
}

# GMI 模型說明（2026-09）：generate 只多收 output_format（PNG／JPEG），edit 連 output_format 都沒有（輸出 PNG）；
# 沒有透明背景、內容審核的參數。價格按尺寸分級，pricing_details 只列 1024x1024 和 1024x1536（公開文件的價格表是舊的）。
# 2026-09 用打不開的參考圖網址實測（不收費）：尺寸限制和 2.5 相同，其他尺寸（例如 2048x2048）也收；
# edit 的 image 送陣列也收（上游用 image[] 送出）；size 不收 auto。
GPT_IMAGE_2 = {
    **GPT_IMAGE,
    "id": "gpt-image-2", "label": "GPT Image 2",
    "generate": "gpt-image-2-generate", "edit": "gpt-image-2-edit",
    "summary": "上一代：品質只有低／中／高、不能透明背景，GMI 上的價格比 2.5 高",
    "qualities": ["low", "medium", "high"],
    "tier_sizes": {"1K": {"2:3": "1024x1536", "3:2": "1536x1024"}},  # 照算的話是 832x1248，沒有公開價格
    "extra_params": {"generate": ["output_format"], "edit": []},
    "formats": ["png", "jpeg"], "transparent_formats": [],
    "backgrounds": [], "moderation": [],
    "price_rule": "sizes",
    "prices": {"1024x1024": {"low": 0.010, "medium": 0.060, "high": 0.220},
               "1024x1536": {"low": 0.020, "medium": 0.120, "high": 0.440}},
    "ref_price": 0, "token_prices": None,
}

# Gemini 3 Pro Image（Google 的 Nano Banana Pro，GMI 經 Vertex AI 呼叫）。GMI 模型說明（2026-09）：
# - 只有一個 ID：payload 有 image（參考圖網址的陣列，最多 14 張）就是改圖、合成，沒有就是文字生圖。
# - 不能指定寬高：只收 aspect_ratio（下面 8 種，沒有 2:3、3:2）和 image_size（1K／2K／4K），
#   實際尺寸照 Google 文件的對照表（_GEMINI_1K；2K、4K 是兩倍、四倍）。
# - 沒有品質、張數、背景、內容審核的參數；輸出格式的參數叫 image_output_format（PNG／JPEG）。
# - 提示詞約 2000 字以內；參考圖每張 ≤ 7 MB（Google 說其中最多 5 張能保留人物的樣子）。
# - 另有多輪編輯（payload 的 contents，回應的 outcome.next_turn_contents），這裡沒有用。
# - 價格（pricing_details）：輸出 1K／2K 每張 $0.134、4K 每張 $0.24；每張參考圖另收 $0.0011。
_GEMINI_1K = {"1:1": (1024, 1024), "4:5": (928, 1152), "5:4": (1152, 928), "3:4": (896, 1200), "4:3": (1200, 896),
              "9:16": (768, 1376), "16:9": (1376, 768), "21:9": (1584, 672)}
GEMINI_3_PRO_IMAGE = {
    "kind": "image", "provider": "gmi",
    "id": "gemini-3-pro-image", "label": "Gemini 3 Pro Image",
    "generate": "gemini-3-pro-image", "edit": "gemini-3-pro-image",
    "summary": "Google 的 Nano Banana Pro：寫實、圖中文字、多張參考圖合成強；不能自訂寬高，一次一張",
    "prompt_required": True, "prompt_max": 2000,
    "media": {"reference_image": 14}, "media_total": 14,
    "labels": {"image": "Image "},
    "image": {"formats": ["jpg", "png"], "max_mb": 7},
    "clip": {}, "clip_sum": {},
    "sizing": "ratio", "size": None,
    "ratios": list(_GEMINI_1K),
    "tiers": {"1K": {"pixels": 1024 * 1024}, "2K": {"pixels": 2048 * 2048}, "4K": {"pixels": 4096 * 4096}},
    "tier_sizes": {tier: {r: f"{w * k}x{h * k}" for r, (w, h) in _GEMINI_1K.items()}
                   for tier, k in (("1K", 1), ("2K", 2), ("4K", 4))},
    "qualities": [], "n": None,
    "extra_params": {"generate": ["output_format"], "edit": ["output_format"]},
    "format_param": "image_output_format",
    "formats": ["png", "jpeg"], "transparent_formats": [],
    "backgrounds": [], "moderation": [],
    "defaults": {"output_format": "png"},
    "notes": {},
    "price_rule": "tiers",
    "prices": {"1K": 0.134, "2K": 0.134, "4K": 0.24},
    "ref_price": 0.0011, "token_prices": None,
}

MODELS = [GPT_IMAGE_25_SUNBURST, GPT_IMAGE_25_FLARE, GPT_IMAGE_2, GEMINI_3_PRO_IMAGE]  # 網頁的模型選單照這個順序
