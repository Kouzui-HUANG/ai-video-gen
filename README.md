# AI 影片生成

一個在本機執行的 AI 影片和圖片生成工具。透過瀏覽器介面整合 MixRoute 與 GMI Cloud，可使用文字、參考圖片、影片、音訊、首尾幀等素材建立生成任務，並在完成後自動下載 MP4；也能切到「圖片」，用 GMI 的 GPT Image 2.5、GPT Image 2、Gemini 3 Pro Image 或 Seedream 5.0 Pro 生成或修改圖片。

## 功能

- 在同一個介面切換 MixRoute 與 GMI Cloud
- 支援 Wan 3.0、Seedance 2.0、Seedance 2.5 與 MiniMax H3
- 切換「影片／圖片」：用 GPT Image 2.5（Sunburst、Flare）、GPT Image 2、Gemini 3 Pro Image 或 Seedream 5.0 Pro 文字生圖，或依參考圖修改、合成；提示詞和參考圖兩邊共用
- 生成的圖片可一鍵拿去繼續編輯，或當成影片的參考圖、首幀、尾幀
- 提供「參考生成」與「首尾幀」兩種模式
- 支援拖放、選取、貼上圖片或加入公開網址
- 依模型即時檢查解析度、比例、時長、素材數量與格式限制
- 顯示任務進度、匯入既有任務、重用歷史設定
- 預覽送給供應商的 JSON，並在 GMI 模型可取得價格時顯示費用估算
- 任務完成後自動下載影片；重新啟動時會接續查詢未完成任務
- 啟動時自動更新到 GitHub 上的最新版本（右上角齒輪的「選項」可以關閉）
- 任務完成或失敗時跳出系統通知、播放提示音（在「選項」開啟）
- 亮色／暗色主題，或跟隨系統外觀
- 另提供 MixRoute Wan 3.0 的命令列介面

## 支援的 API 與模型

| API | 模型 | 解析度 | 時長 | 備註 |
| --- | --- | --- | --- | --- |
| MixRoute | Wan 3.0 | 480P、720P、1080P | 2–30 秒或自動 | 可選音軌，支援文件與網頁素材 |
| GMI Cloud | Wan 3.0 | 480P、720P、1080P | 2–30 秒 | 一律產生音軌，支援負面提示詞 |
| GMI Cloud | Seedance 2.0 | 480p、720p、1080p | 4–15 秒 | 可選音軌，不接受含擬真人臉的素材 |
| GMI Cloud | Seedance 2.5 | 480p、720p | 4–30 秒 | 可選音軌，不接受含擬真人臉的素材 |
| GMI Cloud | MiniMax H3 | 768P、2K | 4–15 秒 | 一律產生音軌；素材合計最多 12 個；純文字生影片要指定比例；不能指定 Seed |

圖片模型（只有 GMI Cloud）：

| 模型 | 用途 | 輸出尺寸 | 品質 | 備註 |
| --- | --- | --- | --- | --- |
| GPT Image 2.5 Sunburst | 沒有參考圖時文字生圖；有參考圖（最多 16 張）時照提示詞修改或合成 | 寬高為 16 的倍數、每邊 ≤ 3840 px、長寬比 ≤ 3:1、約 0.66–8.3 MP | 低、中、高、超高、最高 | 細節最好、改圖最精準 |
| GPT Image 2.5 Flare | 同上 | 同上 | 同上 | 最快，價格和 Sunburst 相同 |
| GPT Image 2 | 同上 | 同上 | 低、中、高 | 上一代；不能透明背景，文字生圖可輸出 PNG／JPEG、改圖只輸出 PNG；價格較高，而且只公開 1024×1024、1024×1536、1536×1024 的價格 |
| Gemini 3 Pro Image | 沒有參考圖時文字生圖；有參考圖（最多 14 張、每張 ≤ 7 MB）時照提示詞修改或合成 | 只能選比例（1:1、4:5、5:4、3:4、4:3、9:16、16:9、21:9）和 1K／2K／4K，例如 16:9 的 1K 是 1376×768 | 沒有品質選項 | Google 的 Nano Banana Pro；一次一張，輸出 PNG 或 JPEG；提示詞建議 2000 字以內 |
| Seedream 5.0 Pro | 沒有參考圖時文字生圖；有參考圖（最多 10 張、每張 ≤ 30 MB）時照提示詞修改或合成 | 比例＋2K（例如 16:9 是 2720×1536），或自訂寬高：總像素 0.92–4.19 MP、長寬比 ≤ 16:1 | 沒有品質選項 | 字節跳動（BytePlus）的模型；一次一張，輸出 PNG 或 JPEG，可加「AI 浮水印」；非同步，送出後會自動查到完成 |

GMI 把每個 GPT Image 模型拆成 `-generate`（文字生圖）與 `-edit`（改圖）兩個 ID，介面會依有沒有參考圖自動選用；Gemini 3 Pro Image 和 Seedream 5.0 Pro 只有一個 ID，有參考圖就一起送。GPT Image 的尺寸可選比例（1:1、16:9、跟參考圖相同…）加 1K／2K／4K，或自訂寬高；一次可生成 1–10 張，輸出 PNG、JPEG 或 WebP，PNG／WebP 可以有透明背景（GPT Image 2 的限制見上表）。換到不支援目前設定的模型時（例如 GPT Image 2 沒有「最高」品質、Gemini 沒有 2:3 也不能自訂寬高、Seedream 只有 2K），設定本身不會被改掉，送出時才換成可用的值（Gemini 用最接近的比例），並在檢查區說明。

介面會依目前的 API 與模型顯示實際可用選項。完整限制集中定義在 `video_models.py`（影片）與 `image_models.py`（圖片）。

## 系統需求

- Python 3.9 以上
- [`requests`](https://requests.readthedocs.io/)
- 至少一組 MixRoute 或 GMI Cloud API key
- 現代瀏覽器

macOS 可以雙擊 `AI 影片生成.app`，Windows 可以雙擊 `AI 影片生成.cmd`；直接執行 Python 的方式可用於 macOS、Windows 與 Linux。

## 快速開始

### 1. 下載專案

```bash
git clone https://github.com/Kouzui-HUANG/ai-video-gen.git
cd ai-video-gen
```

請用 `git clone` 下載，之後每次啟動才會自動更新到最新版本（需要安裝 git：macOS 可在終端機執行 `xcode-select --install`，Windows 請安裝 [Git for Windows](https://git-scm.com/download/win)）。用 GitHub 的「Download ZIP」下載的也能使用，只是不會自動更新。

### 2. 安裝依賴

建議使用虛擬環境：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install requests
```

Windows PowerShell 啟用虛擬環境的指令為：

```powershell
.venv\Scripts\Activate.ps1
python -m pip install requests
```

Windows 用 `AI 影片生成.cmd` 啟動時，缺少 `requests` 會詢問要不要自動安裝，可以略過這一步。

### 3. 設定 API key

可以先透過環境變數設定：

```bash
export MIXROUTE_API_KEY="你的 MixRoute API key"
export GMI_API_KEY="你的 GMI Cloud API key"
```

只需要設定準備使用的供應商。也可以略過這一步，啟動後按網頁右上角的「API key」輸入；除非勾選「記在這個瀏覽器」，否則 key 只會保存在伺服器記憶體中。

Windows PowerShell 可使用：

```powershell
$env:MIXROUTE_API_KEY="你的 MixRoute API key"
$env:GMI_API_KEY="你的 GMI Cloud API key"
```

`$env:` 只對這個 PowerShell 視窗有效。要讓雙擊 `AI 影片生成.cmd` 啟動的伺服器也讀得到，改用 `setx` 永久設定，之後開啟的程式才會生效：

```powershell
setx GMI_API_KEY "你的 GMI Cloud API key"
```

### 4. 啟動網頁介面

```bash
python3 video_ui.py
```

程式會在本機啟動伺服器並自動開啟 [http://127.0.0.1:8765](http://127.0.0.1:8765)。若不想自動開啟瀏覽器，或需要更換連接埠：

```bash
python3 video_ui.py --port 9000 --no-browser
```

### macOS App

也可以直接雙擊專案根目錄中的 `AI 影片生成.app`。請讓 App 與 `video_ui.py` 保持在同一層；它會在背景啟動伺服器並開啟瀏覽器。

App 啟動的伺服器會在網頁關閉、沒有進行中任務且閒置 10 分鐘後自動結束。啟動記錄位於 `outputs/video_ui.log`。若要改用其他連接埠，可在啟動環境設定 `VIDEO_UI_PORT`。

### Windows 一鍵啟動

雙擊專案根目錄的 `AI 影片生成.cmd`（檔案總管預設隱藏副檔名，會顯示成「AI 影片生成」）。它和 macOS App 一樣：伺服器沒在跑就在背景啟動，準備好後打開瀏覽器。啟動時會出現一個小視窗顯示進度，打開瀏覽器後自動關閉；沒有啟動成功時，視窗會留著顯示原因和記錄的最後幾行。`AI 影片生成.app` 資料夾是 macOS 用的，Windows 上用不到。

- **Python**：優先使用專案裡的 `.venv`，其次是 `python` 指令或 `py` 啟動器找到的 Python 3.9 以上版本。缺少 `requests` 時會詢問要不要用 pip 安裝；完全找不到 Python 時，會說明安裝方式並可直接打開 python.org 的下載頁。
- **背景執行**：伺服器在背景執行，不會出現視窗，和 App 一樣在網頁關閉、沒有進行中任務且閒置 10 分鐘後自動結束。要馬上結束，可以在工作管理員結束「Python」。
- **記錄與連接埠**：啟動記錄同樣寫在 `outputs\video_ui.log`；要改用其他連接埠，設定環境變數 `VIDEO_UI_PORT`（例如 `setx VIDEO_UI_PORT 9000`）。
- 連續雙擊好幾次也只會啟動一個伺服器。
- 用 ZIP 下載、解壓縮的，第一次雙擊可能出現「無法驗證發行者」的安全性警告，按「執行」即可。

## 使用方式

1. 在右上角選擇 API 與模型，確認 API key 已設定。
2. 選擇「參考生成」或「首尾幀」。
3. 加入提示詞與素材。不同模型可接受的素材與數量會直接顯示在畫面上。
4. 設定解析度、比例、時長、音軌、Seed 等參數。
5. 修正畫面列出的檢查訊息，必要時先用「預覽請求 JSON」確認內容。
6. 按「生成影片」或使用 `⌘ / Ctrl + Enter`。
7. 在右側查看進度。成功後影片會自動下載到 `outputs/`。

如已有 task ID 或 request ID，可在任務區輸入 ID 接續查詢。從任務列表移除紀錄不會刪除已下載的影片。

### 生成圖片

1. 在右上角把「生成」切到「圖片」，選 GPT Image 2.5 Sunburst、Flare、GPT Image 2、Gemini 3 Pro Image 或 Seedream 5.0 Pro（API 固定是 GMI Cloud）。
2. 輸入提示詞。要修改或合成圖片時加入參考圖，在提示詞用「Image 1」「Image 2」指稱。
3. 設定比例與尺寸、品質、張數、格式與背景（Gemini 只有比例、解析度和格式；Seedream 沒有品質和張數，可加 AI 浮水印）；檢查區會顯示這次用哪個模型 ID 和預估費用。
4. 按「生成圖片」。圖片生成完會自動下載到 `outputs/`，並顯示在右側任務區。
5. 點圖片可以放大檢視，並選擇「繼續編輯這張」「當影片參考圖」「當影片首幀」或「當影片尾幀」。

提示詞與參考圖片在影片和圖片之間共用，切換時不會消失；影片和圖片的其他參數各自保留。

GPT Image 2.5、GPT Image 2 和 Gemini 3 Pro Image 都是同步模型：GMI 要等圖片生成完才回應，通常需要十幾秒到數分鐘。等待期間連線中斷或伺服器重啟時，程式會從 GMI 的請求列表找回同一個請求，不會重新送出、重複收費。Seedream 5.0 Pro 是非同步模型：送出後馬上拿到 request ID，再像影片一樣查到完成，伺服器重啟後會接著查。

## 選項與自動更新

按右上角的齒輪打開「選項」：

- **主題**：跟隨系統、亮色或暗色。
- **語言**：目前只有繁體中文，English 之後推出。
- **啟動時自動更新**：預設開啟。
- **任務完成時通知**：預設關閉。影片或圖片生成完成、失敗（包括下載失敗、查詢中斷）時跳出系統通知；打開時瀏覽器會詢問是否允許。按「測試」可以馬上看一則測試通知。
- **提示音**：預設關閉。任務完成或失敗時播放提示音，兩種聲音不同；按「試聽」可以先聽聽看。

選項存在 `outputs/settings.json`，同一台電腦不管用哪個瀏覽器開都一樣，在一個分頁改了，其他開著的分頁也會跟著改。標「即將推出」的儲存、預設值目前只是先留位置。

通知的做法：

- 通知和提示音是網頁發出的，網頁要開著，但可以放在背景（切到別的分頁或程式、縮小視窗都可以）；關掉網頁就不會通知。
- 網頁在背景時跳系統通知，正在看網頁時改在右下角提示。點系統通知會回到網頁，並標出是哪一個任務。
- 開著好幾個分頁時（每次開 App 都會開一個新分頁），每個任務只會通知一次、響一次。
- 打開網頁時就已經結束的任務不會通知。

自動更新的做法：

- 每次啟動時比對本機和 GitHub 上 `main` 分支的最新 commit。版本號就是 commit 的日期加上短代碼，例如 `2026.09.27（7832df3）`。
- 有新版時用 git 快轉（fast-forward）更新、自動重新啟動載入新版，之後才打開網頁；沒有新版時啟動大約多花 1 秒。連不到 GitHub 時直接用目前的版本啟動。
- 下列情況只提醒、不更新，不會動到你的修改：不是用 `git clone` 下載的、不在 `main` 分支、有還沒 commit 的修改、有還沒推上 GitHub 的 commit。GitHub 上有新版卻沒更新時，齒輪上會出現小圓點，原因寫在選項的「更新」區。
- 更新後會先試著載入新版；如果新版需要還沒安裝的套件，會退回原本的版本，並在選項裡說明要安裝什麼。
- 伺服器開著的時候不會自己檢查。可以在選項按「檢查更新」，有新版時按「立即更新並重新啟動」，網頁會在伺服器重新啟動後自動重新整理。有圖片正在等 GMI 生成時要等它完成；進行中的影片任務會在重新啟動後接著查詢。
- 每次檢查的結果會寫在啟動記錄（`outputs/video_ui.log` 或終端機）。

## 命令列用法

命令列模式目前只支援 MixRoute Wan 3.0，並需要 `MIXROUTE_API_KEY`：

```bash
python3 mixroute_video.py "一隻橘貓在窗台上伸懶腰"
```

指定參數與輸出檔：

```bash
python3 mixroute_video.py \
  "海浪拍打礁岩，空拍鏡頭" \
  --resolution 720P \
  --ratio 9:16 \
  --duration 5 \
  --audio \
  --output outputs/ocean.mp4
```

接續查詢已建立的任務，不會重複送出：

```bash
python3 mixroute_video.py --task-id <task_id>
```

查看所有選項：

```bash
python3 mixroute_video.py --help
```

## 素材與隱私

本機伺服器只監聽 `127.0.0.1`，不會直接對區域網路或網際網路開放。不過，素材仍可能依所選 API 送往外部服務：

- **MixRoute**：本機圖片轉為 base64 後直接送出；本機影片、音訊與文件會先上傳至 [Litterbox](https://litterbox.catbox.moe/) 取得 1–72 小時的臨時公開網址。
- **GMI Cloud**：本機圖片、影片與音訊會上傳至 GMI 的儲存空間並取得公開網址；GMI 模式不支援文件或網頁素材。生成圖片時的參考圖也一樣。
- 公開網址在有效期間內可被持有網址的人存取，請勿上傳敏感或未獲授權的內容。
- 加入過的本機素材會以內容雜湊命名，保留副本於 `outputs/inputs/`，供重用設定或重新上傳使用。
- 若在 API key 對話框勾選「記在這個瀏覽器」，key 會存進該瀏覽器的 localStorage；共用電腦上不建議啟用。

## 輸出與資料

```text
outputs/
├── <task_id>.mp4          # 完成後下載的影片
├── <request_id>.png       # 生成的圖片（副檔名依輸出格式；一次多張時為 <request_id>-1.png、-2.png…）
├── tasks.json             # 任務紀錄
├── settings.json          # 選項（主題、語言、自動更新、通知、提示音）
├── inputs/                # 本機素材副本
├── video_ui.log           # macOS App 和 Windows 啟動器的背景啟動記錄
└── launcher.lock          # Windows 啟動器用來避免重複啟動的空檔案
```

`outputs/` 是執行資料，不是程式碼。備份或清理前請先確認是否仍需要任務紀錄、影片及素材副本。

## 專案結構

```text
.
├── video_ui.py        # 本機 HTTP 伺服器、任務管理、素材處理與下載
├── video_ui.html      # 瀏覽器介面
├── video_models.py    # 影片模型能力、預設值與素材限制
├── image_models.py    # 圖片模型（GPT Image 2.5、GPT Image 2、Gemini 3 Pro Image、Seedream 5.0 Pro）的參數範圍與價格
├── mixroute_video.py  # MixRoute API 實作與 CLI
├── gmi_video.py       # GMI Cloud API、上傳與狀態轉換
├── gmi_image.py       # GMI Cloud 圖片生成（同步請求、找回請求、下載）
├── updater.py         # 自動更新：比對 GitHub 上的最新版本，用 git 快轉
├── AI 影片生成.app/   # macOS 雙擊啟動器
├── AI 影片生成.cmd    # Windows 雙擊啟動器：找到 Python 後執行 windows/launcher.py
└── windows/
    └── launcher.py    # Windows 啟動器本體：背景啟動伺服器、等它準備好、打開瀏覽器
```

若要新增影片模型，先在 `video_models.py` 加入模型規格；圖片模型則加在 `image_models.py`。若 payload 格式不同，再於對應的 API 模組處理轉換。

## 常見問題

### `ModuleNotFoundError: No module named 'requests'`

請確認目前使用的 Python 已安裝依賴：

```bash
python3 -m pip install requests
```

Windows 請改用 `py -m pip install requests`。

### 8765 連接埠已被占用

改用其他連接埠：

```bash
python3 video_ui.py --port 9000
```

### 關閉後任務還沒完成

任務 ID 與狀態會保存在 `outputs/tasks.json`。下次啟動且對應 API key 可用時，程式會自動接續查詢；也可以在介面中用任務 ID 匯入。

### macOS App 沒有啟動

確認 App 與 `video_ui.py` 位於同一個資料夾，且某個 `python3` 已安裝 `requests`。詳細錯誤可查看 `outputs/video_ui.log`。

### Windows 雙擊 `AI 影片生成.cmd` 沒有啟動

啟動視窗會留著顯示原因和 `outputs\video_ui.log` 的最後幾行。常見的有：

- 找不到 Python：到 [python.org](https://www.python.org/downloads/windows/) 安裝 Python 3.9 以上版本，裝好後再雙擊一次。
- 連接埠被占用：可能是別的程式用了 8765，設定環境變數 `VIDEO_UI_PORT` 換一個（例如 `setx VIDEO_UI_PORT 9000`，設定後再雙擊一次）。
- 超過 60 秒還沒準備好：通常是正在下載新版本，等一下再雙擊一次。

### 沒有跳出通知或沒有提示音

- 網頁要開著（可以在背景）。關掉網頁後就不會通知。
- 在「選項」按通知旁的「測試」。瀏覽器封鎖了通知時，選項裡會說明：到瀏覽器的網站設定，把 `127.0.0.1` 的「通知」改成允許，再重新整理網頁。
- 瀏覽器允許了卻看不到通知：macOS 到「系統設定 › 通知」，確認瀏覽器（例如 Google Chrome、Safari）可以顯示通知；Windows 到「設定 › 系統 › 通知」。勿擾或專注模式也會擋住通知。
- 沒有聲音：瀏覽器規定網頁要先被點過才能出聲。App 剛打開、還沒點過的網頁不會響，在網頁上任意點一下就好。

### 右上角沒有「影片／圖片」切換或齒輪

正在執行的是更新前的 `video_ui.py`。請結束它再重新開啟：終端機執行的按 `Ctrl + C`；App 或 Windows 啟動器啟動的會在網頁關閉、沒有進行中任務且閒置 10 分鐘後自動結束。

### 沒有自動更新

打開右上角齒輪的「選項」，「更新」區會寫出原因。常見的有：

- 本機有還沒 commit 的修改：commit 或還原後，下次啟動就會更新。
- 本機和 GitHub 上各有新的 commit：在終端機執行 `git pull` 手動合併。
- 用 ZIP 下載的：用 `git clone` 重新下載，再把原本的 `outputs/` 資料夾搬過去。

### 圖片生成失敗：Generation rejected

GMI 會把上游拒絕的原因統一回報成這句話。常見原因是提示詞或參考圖沒通過內容審核（可改寫提示詞，或勾選「寬鬆審核」再試）、參考圖網址打不開，或參數組合不被接受。

## 參考文件

- [MixRoute Wan 3.0 Video API](https://docs.mixroute.ai/en/model-api/alibaba/wan3.0-video)
- [GMI Cloud Video API](https://docs.gmicloud.ai/inference-engine/api-reference/video-api-reference)
- [GMI Cloud Seedance 2.0](https://docs.gmicloud.ai/model-quickstarts/video/seedance-2-0-260128)
- [GMI Cloud MiniMax-H3](https://docs.gmicloud.ai/model-quickstarts/video/minimax-h3)（只列欄位名稱；參數範圍與素材限制見 [MiniMax 官方 API 文件](https://platform.minimax.io/docs/api-reference/video-generation-v2-create)）
- [GMI Cloud gpt-image-2-edit](https://docs.gmicloud.ai/model-quickstarts/image/gpt-image-2-edit)（GPT Image 2.5 沿用相同格式；這頁的價格表已經過時，兩代的完整說明與目前價格在 GMI 主控台的模型頁）
- [OpenAI GPT-Image-2.5 Sunburst](https://developers.openai.com/api/docs/models/gpt-image-2.5-sunburst)
- [GMI Cloud gemini-3-pro-image](https://docs.gmicloud.ai/model-quickstarts/image/gemini-3-pro-image)（各比例、解析度實際輸出的尺寸見 [Google 的圖片生成文件](https://ai.google.dev/gemini-api/docs/image-generation)）
- [GMI Cloud seedream-5.0-pro](https://docs.gmicloud.ai/model-quickstarts/image/seedream-5-0-pro)（2026-09 這頁和模型說明是從 5.0 lite 複製的，3K、組圖、14 張參考圖都是 lite 的規格；5.0 pro 的實際規格見 [BytePlus 的 Seedream 5.0 pro 教學](https://docs.byteplus.com/en/docs/ModelArk/2582774)）

影片和圖片生成都會使用供應商額度並可能產生費用；送出前請確認目前價格與帳戶餘額。

GPT Image 2.5 的費用在 GMI 建立請求時預扣，預扣金額就是實際費用：1024×1024 每張約為低 $0.006、中 $0.013、高 $0.053、超高 $0.094、最高 $0.211，其他尺寸依像素數等比例換算；改圖時每張參考圖最多另加約 $0.012。品質設為 auto 時 GMI 會以最高品質計價，因此介面不提供 auto。

GPT Image 2 按尺寸計價，GMI 目前公開的每張價格為：1024×1024 低 $0.010、中 $0.060、高 $0.220；1024×1536／1536×1024 低 $0.020、中 $0.120、高 $0.440。介面的比例選 1:1、2:3、3:2 加 1K 時會對上這些尺寸；其他尺寸 GMI 也接受，但沒有公開價格，檢查區會提醒，實際費用請到 GMI 後台確認。

Gemini 3 Pro Image 按解析度計價：1K、2K 每張 $0.134，4K 每張 $0.24；改圖時每張參考圖另加 $0.0011。

Seedream 5.0 Pro 每張 $0.085，不分尺寸。
