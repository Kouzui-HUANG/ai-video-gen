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
- 生成的影片和圖片可以改存到自己選的資料夾（在「選項」變更）
- 檔名看得懂：「日期_時間_模型_名稱」，例如 `2026-09-28_1432_Seedance2.5_橘貓伸懶腰.mp4`；名稱可以送出前取、之後改，沒取就用提示詞的開頭
- 生成設定記在檔案裡，把檔案拖回任務區就能還原當時的模型、提示詞、參數和素材
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
| Gemini 3 Pro Image | 沒有參考圖時文字生圖；有參考圖（最多 14 張、每張 ≤ 7 MB）時照提示詞修改或合成 | 只能選比例（1:1、4:5、5:4、3:4、4:3、9:16、16:9、21:9）和 1K／2K／4K，例如 16:9 的 1K 是 1376×768 | 沒有品質選項 | Google 的 Nano Banana Pro；模型一次生成一張，多張時自動分成多個請求送出；輸出 PNG 或 JPEG；提示詞建議 2000 字以內 |
| Seedream 5.0 Pro | 沒有參考圖時文字生圖；有參考圖（最多 10 張、每張 ≤ 30 MB）時照提示詞修改或合成 | 比例＋2K（例如 16:9 是 2720×1536），或自訂寬高：總像素 0.92–4.19 MP、長寬比 ≤ 16:1 | 沒有品質選項 | 字節跳動（BytePlus）的模型；模型一次生成一張，多張時自動分成多個請求送出；輸出 PNG 或 JPEG，可加「AI 浮水印」；非同步，送出後會自動查到完成 |

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
6. 需要的話在「名稱」幫這次的任務取名（見下面的「檔名與還原設定」），下面會顯示這次會存成什麼檔名。
7. 按「生成影片」或使用 `⌘ / Ctrl + Enter`。
8. 在右側查看進度。成功後影片會自動下載到輸出資料夾（預設是 `outputs/`，可在「選項」變更）。

如已有 task ID 或 request ID，可在任務區輸入 ID 接續查詢。從任務列表移除紀錄不會刪除已下載的影片。

### 生成圖片

1. 在右上角把「生成」切到「圖片」，選 GPT Image 2.5 Sunburst、Flare、GPT Image 2、Gemini 3 Pro Image 或 Seedream 5.0 Pro（API 固定是 GMI Cloud）。
2. 輸入提示詞。要修改或合成圖片時加入參考圖，在提示詞用「Image 1」「Image 2」指稱。
3. 設定比例與尺寸、品質、張數、格式與背景（Gemini 沒有品質和背景；Seedream 沒有品質和背景，可加 AI 浮水印）；檢查區會顯示這次用哪個模型 ID 和預估費用。
4. 按「生成圖片」。圖片生成完會自動下載到輸出資料夾（預設是 `outputs/`），並顯示在右側任務區。
5. 點圖片可以放大檢視，並選擇「繼續編輯這張」「當影片參考圖」「當影片首幀」或「當影片尾幀」。

提示詞與參考圖片在影片和圖片之間共用，切換時不會消失；影片和圖片的其他參數各自保留。

GPT Image 2.5、GPT Image 2 和 Gemini 3 Pro Image 都是同步模型：GMI 要等圖片生成完才回應，通常需要十幾秒到數分鐘。等待期間連線中斷或伺服器重啟時，程式會從 GMI 的請求列表找回同一個請求，不會重新送出、重複收費。Seedream 5.0 Pro 是非同步模型：送出後馬上拿到 request ID，再像影片一樣查到完成，伺服器重啟後會接著查。

Gemini 3 Pro Image 和 Seedream 5.0 Pro 一次只生成一張。張數設成 2 以上時，程式會把同一個請求在背景送出多次（最多同時 4 個），結果放在同一個任務裡，做好一張就顯示一張；其中幾張失敗時，成功的照樣保留，失敗的原因寫在任務上（失敗的不收費）。

### 檔名與還原設定

生成的影片和圖片存成「日期_時間_模型_名稱」：

```text
2026-09-28_1432_Seedance2.5_橘貓伸懶腰.mp4
2026-09-28_1432_Seedance2.5_橘貓伸懶腰_2.mp4       ← 同一分鐘又送出同名的任務
2026-09-28_1440_GPT2.5-Sunburst_橘貓海報-1.png     ← 一次多張的第 1 張
```

- **時間**是送出的時間，**模型**是簡短的模型名稱，**名稱**是送出前在「名稱」填的（最多 40 字，檔名不能用的 `\ / : * ? " < > |` 會拿掉）。
- 沒取名時用提示詞的開頭：第一句話，最多約 20 個中文字或 40 個英文字母。提示詞開頭是 `summary:`、`title:` 這類欄位時（例如 YAML 格式的提示詞），改用欄位的內容。沒有提示詞就只有日期、時間和模型。
- **改名**：點任務卡片上名稱旁的鉛筆，檔案跟著改名（日期、時間和模型不變）。已經匯入剪輯軟體的檔案，改名後要在剪輯軟體裡重新連結。還在生成的任務改名後，下載時就用新的名稱。
- 更新前下載的檔案維持原本的檔名（`<task_id>.mp4`、`<request_id>.png`）；要改成新的格式，在任務卡片上改名即可。

**從檔案還原設定**：把生成的影片或圖片拖到右邊的任務區（拖到左邊是加入素材），或按任務區的「從檔案還原…」，就會把當時的模型、提示詞、參數、名稱和素材載入到左邊，和「重用設定」一樣。

- 任務還在列表上時直接用那筆紀錄，並標出是哪個任務；檔案在 Finder 或檔案總管裡改過名、搬過資料夾也認得（比對檔案內容）。
- 任務從列表移除了、或檔案是從別台電腦拿來的，靠檔案裡記下的生成設定還原；素材要這台電腦上有（`outputs/inputs/` 的副本，或當初貼的公開網址），找不到的會列出來請你重新加入。
- 生成設定寫在檔案裡不影響播放或顯示：圖片寫在 PNG、JPEG、WebP 的中繼資料，影片附加在 MP4 檔尾。
- **有 AI 內容憑證的圖片不寫**：GPT Image（Azure OpenAI）等供應商會在圖片裡放簽章過的內容憑證（C2PA），標明這是 AI 生成的；憑證涵蓋整個檔案，寫進任何資料都會讓它失效。這些圖片一律不動，改用任務紀錄比對檔案內容，所以任務從列表移除或換電腦之後就還原不了。影片的憑證（例如 Seedance）不檢查 MP4 檔尾的 free 區塊，設定寫在那裡，憑證照樣有效。

## 選項與自動更新

按右上角的齒輪打開「選項」：

- **主題**：跟隨系統、亮色或暗色。
- **語言**：目前只有繁體中文，English 之後推出。
- **啟動時自動更新**：預設開啟。
- **任務完成時通知**：預設關閉。影片或圖片生成完成、失敗（包括下載失敗、查詢中斷）時跳出系統通知；打開時瀏覽器會詢問是否允許。按「測試」可以馬上看一則測試通知。
- **提示音**：預設關閉。任務完成或失敗時播放提示音，兩種聲音不同；按「試聽」可以先聽聽看。
- **輸出資料夾**：生成的影片和圖片存放的位置，預設是專案裡的 `outputs/`。按「變更…」會跳出選擇資料夾的視窗；也可以改成直接輸入路徑（資料夾不存在時會自動建立）。按「打開」在 Finder 或檔案總管打開它，「改回預設」回到 `outputs/`。
- **在檔案裡記下生成設定**：預設開啟。把模型、提示詞和參數寫進生成的影片和圖片，之後拖回任務區就能還原（見「檔名與還原設定」）。直接把原始檔傳給別人時，對方也讀得到這些設定；不想這樣的話可以關掉，關掉後只影響之後的檔案，還原改靠任務紀錄比對檔案內容。

選項存在 `outputs/settings.json`，同一台電腦不管用哪個瀏覽器開都一樣，在一個分頁改了，其他開著的分頁也會跟著改。標「即將推出」的預設值目前只是先留位置。

輸出資料夾的做法：

- 變更後只影響之後下載的檔案；之前的檔案留在原本的資料夾，任務列表照樣看得到、播得到。自己把舊檔案搬到新的輸出資料夾也找得到。
- 只有影片和圖片會存到輸出資料夾；任務紀錄、選項和素材副本一律留在專案的 `outputs/`。
- 選的資料夾暫時不能用時（例如外接硬碟沒接上、沒有寫入權限），新的檔案會先存到 `outputs/`，任務上會註明，選項裡也會提醒；生成結果的網址會過期，所以不會因為資料夾的問題就下載失敗。資料夾被刪掉的話，下次存檔時會重新建立。

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
- 生成的影片和圖片裡會記下模型、提示詞、參數和素材的檔名（不含上傳到 GMI 或 Litterbox 的網址），直接把原始檔傳給別人時對方讀得到；社群平台上傳時多半會重新壓縮，這些資料就不見了。不想記的話在「選項」關掉「在檔案裡記下生成設定」。
- 若在 API key 對話框勾選「記在這個瀏覽器」，key 會存進該瀏覽器的 localStorage；共用電腦上不建議啟用。

## 輸出與資料

```text
outputs/
├── 2026-09-28_1432_Seedance2.5_橘貓伸懶腰.mp4   # 完成後下載的影片（日期_時間_模型_名稱）
├── 2026-09-28_1440_GPT2.5-Sunburst_海報-1.png  # 生成的圖片（副檔名依輸出格式；一次多張時加 -1、-2…）
├── tasks.json             # 任務紀錄（也記著每個檔案的大小和 SHA-256，拖回網頁時比對用）
├── settings.json          # 選項（主題、語言、自動更新、通知、提示音、輸出資料夾、在檔案裡記下生成設定）
├── inputs/                # 本機素材副本
├── video_ui.log           # macOS App 和 Windows 啟動器的背景啟動記錄
└── launcher.lock          # Windows 啟動器用來避免重複啟動的空檔案
```

在選項換了輸出資料夾的話，之後下載的影片和圖片存在那個資料夾，其他檔案照樣在 `outputs/`。

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
├── media_meta.py      # 把生成設定寫進、讀出影片和圖片檔（PNG、JPEG、WebP、MP4），不動有內容憑證的圖片
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

### 生成的檔案沒有存到選的輸出資料夾

選的資料夾不能用時，檔案會先存到專案的 `outputs/`，任務上會寫出原因；打開「選項」也會看到提醒。常見的有：

- 外接硬碟或網路磁碟沒接上：接上後，之後的檔案就會存回選的資料夾。已經存到 `outputs/` 的可以自己搬過去，任務列表照樣找得到。
- macOS 沒有取用權限：「桌面」「文件」「下載項目」、iCloud 雲碟和外接硬碟裡的資料夾，第一次使用時 macOS 會詢問能不能取用。拒絕過的話，到「系統設定 › 隱私權與安全性 › 檔案與檔案夾」允許「AI 影片生成」（從終端機啟動的是「終端機」），或改選其他資料夾。

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

### 把檔案拖回網頁沒有還原設定

- 要拖到右邊的任務區；拖到左邊是加入素材。
- 檔案裡沒有生成設定、任務列表裡也找不到時沒辦法還原，常見的有：任務從列表移除了，而檔案是有內容憑證的圖片（這種圖片不寫設定）或關掉「在檔案裡記下生成設定」後產生的；檔案在社群平台、通訊軟體或剪輯軟體裡重新壓縮過（內容變了，設定也不見了）。
- 更新前下載的檔案裡沒有生成設定，任務還在列表上時仍然可以還原。

### 右上角沒有「影片／圖片」切換或齒輪

正在執行的是更新前的 `video_ui.py`。請結束它再重新開啟：終端機執行的按 `Ctrl + C`；App 或 Windows 啟動器啟動的會在網頁關閉、沒有進行中任務且閒置 10 分鐘後自動結束。

### 沒有自動更新

打開右上角齒輪的「選項」，「更新」區會寫出原因。常見的有：

- 本機有還沒 commit 的修改：commit 或還原後，下次啟動就會更新。
- 本機和 GitHub 上各有新的 commit：在終端機執行 `git pull` 手動合併。
- 用 ZIP 下載的：用 `git clone` 重新下載，再把原本的 `outputs/` 資料夾搬過去。

### 圖片生成失敗：Generation rejected

GMI 會把上游拒絕的原因統一回報成這句話（GPT Image 2.5 和 Gemini 3 Pro Image 都是）。常見原因是提示詞或參考圖沒通過內容審核（可改寫提示詞；GPT Image 2.5 也可以勾選「寬鬆審核」再試）、參考圖網址打不開，或參數組合不被接受。

### Seedream 生成失敗：Backend error (400)

BytePlus 在送出時就拒絕了這個請求，GMI 沒有轉告原因，請求也沒有建立，不收費。常見原因是參考圖網址打不開、提示詞或參考圖沒通過審核，或尺寸不被接受；可以先換掉參考圖、改用 2K 的預設比例再試。

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
