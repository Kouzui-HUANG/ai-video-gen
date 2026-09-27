"""GMI Cloud 上能用的圖片模型（GPT Image 2.5、GPT Image 2），以及參數範圍與價格。

網頁（video_ui.html）的「圖片」模式依這份資料畫出參數表單、即時檢查和估價；伺服器（video_ui.py）送出前用同一份資料再檢查一次。
模型說明：GET https://console.gmicloud.ai/api/v1/ie/requestqueue/apikey/models/<model>
（公開文件站 2026-09 只有 https://docs.gmicloud.ai/model-quickstarts/image/gpt-image-2-edit，價格已經過時，以模型說明為準）。
新增模型：在 MODELS 加一筆；payload 格式不同的話，再到 gmi_image.py 處理。

每個模型在 GMI 上拆成兩個 ID：沒有參考圖時送 generate（文字生圖），有參考圖時送 edit（照提示詞修改或合成參考圖）。
Sunburst 和 Flare 的參數、價格完全相同，差別只在上游的模型（Sunburst 細節和改圖精準度最好，Flare 最快）。
GPT Image 2 是上一代，參數比較少，價格按尺寸分級（見 GPT_IMAGE_2 上面的說明）。

欄位：
- generate／edit：兩個 GMI 模型 ID；summary：模型選單的說明。
- media：參考圖最多幾張（edit 的 image 可以送最多 16 張的陣列）；labels：提示詞裡指稱參考圖的寫法，後面直接接編號。
- image：參考圖的格式和大小（OpenAI 沒有限制尺寸，只要 ≤ 50 MB；本機圖片經 GMI 的上傳 API，只能是 JPEG／PNG）。
- size：輸出尺寸的規則：寬高都是 multiple 的倍數、每邊 ≤ max_side、長寬比 ≤ max_ratio、總像素在 min_pixels–max_pixels。
  ratios、tiers 是網頁上的比例和解析度選項（tiers：pixels＝總像素約多少，long＝長邊多長，超過上限時等比例縮小）；
  tier_sizes：某個解析度＋比例直接用指定的尺寸，不照 tiers 算（GPT Image 2 用來對上有公開價格的尺寸）。
- qualities：品質。auto 不列出來：GMI 對 auto（或不送）一律按最高品質計價。
- extra_params：除了 prompt、image、size、quality、n 以外，generate／edit 各收哪些參數（output_format、output_compression、
  background、moderation）；沒列的不送，網頁上會說明這次用什麼。
- formats：輸出格式；transparent_formats：能輸出透明背景的格式；backgrounds、moderation：可選的值（空的＝不支援）；
  n：一次生成幾張；defaults：「恢復預設」和模型不支援使用者的選擇時用的值。
- price_rule、prices：每張的價格（美元）。"pixels"：prices 是 1024×1024 的價格，其他尺寸按像素數等比例換算；
  "sizes"：prices 是「寬x高（小的在前）→ 品質 → 價格」，沒列的尺寸 GMI 接受但沒有公開價格。
  GMI 建立請求時預扣費用。驗證 key 時會用模型說明的 pricing_details 更新 prices。
- ref_price：edit 每張參考圖最多加收的費用；token_prices：每百萬 token 的價格（text＝提示詞，約 3 bytes 一個 token；
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
    "size": SIZE,
    "ratios": ["1:1", "4:3", "3:4", "3:2", "2:3", "16:9", "9:16", "21:9"],
    "tiers": {"1K": {"pixels": 1024 * 1024}, "2K": {"long": 2048}, "4K": {"long": 3840}},
    "n": {"min": 1, "max": 10},
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

MODELS = [GPT_IMAGE_25_SUNBURST, GPT_IMAGE_25_FLARE, GPT_IMAGE_2]  # 網頁的模型選單照這個順序
