"""把生成設定寫進生成的影片和圖片檔，之後把檔案拖回網頁就能還原（網頁的 readMeta 讀同樣的格式）。

內容是一段 UTF-8 的 JSON（video_ui.py 的 build_meta 組出來，"app" 欄位是 KEY），依檔案格式放在：
- MP4：檔尾一個頂層的 free box，內容以 MP4_UUID 開頭。其他 box 都不動，影片資料的位置（stco／co64）不受影響，
  播放器本來就會略過 free box。
- PNG：IHDR 後面的 iTXt，關鍵字是 KEY，不壓縮。
- JPEG：開頭的 APPn（JFIF、EXIF…）後面的 COM 段，內容以 AIVG、第幾段、共幾段開頭；
  一段最多 65533 bytes，JSON 太長時分成好幾段。
- WebP：最後一個 AIVG chunk。規格只允許延伸格式（有 VP8X）放未知的 chunk，簡單格式（只有 VP8／VP8L）先補上 VP8X。

供應商的內容憑證（C2PA，證明是 AI 生成的簽章）不能被弄壞：
- 圖片的憑證（PNG 的 caBX、JPEG 的 APP11、WebP 的 C2PA chunk）涵蓋整個檔案，改任何一個 byte 都會失效，
  有憑證的圖片一律不寫（write 回傳 "signed"），靠任務紀錄的檔案雜湊還原。
- 影片的憑證（C2PA_UUID 的 uuid box）不檢查列在 exclusions 裡的 box；BytePlus（Seedance）的有列 /free，
  所以寫在 free box 裡憑證照樣有效（2026-09 用 c2pa-python 驗證過）。沒列 /free 的就不寫。
每次都是重寫：之前寫的（例如改名前）先拿掉再寫新的。
"""
import json
import os
import struct
import zlib
from pathlib import Path

KEY = "ai-video-gen"
PNG_SIG = b"\x89PNG\r\n\x1a\n"
JPEG_TAG = b"AIVG"
JPEG_MAX = 65533 - len(JPEG_TAG) - 2  # 一個 COM 段放得下的 JSON（段長 2 bytes，再扣掉 AIVG、第幾段、共幾段）
WEBP_CHUNK = b"AIVG"
MP4_UUID = bytes.fromhex("429e443e5b154a5c9aea2b34b4828c77")  # 放在我們的 free box 開頭，分得出是不是我們寫的
C2PA_UUID = bytes.fromhex("d8fec3d61b0e483c92975828877ec481")  # MP4 裡放 C2PA 憑證的 uuid box
C2PA_MAX = 16 << 20  # 讀影片憑證的上限（一般只有幾十 KB）

WRITTEN, SIGNED, UNSUPPORTED = "written", "signed", "unsupported"  # write 的結果：寫好了、有憑證不寫、格式不支援


def kind_of(head):
    """看檔案開頭認格式：png、jpeg、webp、mp4，認不出來是 None。"""
    if head.startswith(PNG_SIG):
        return "png"
    if head[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head[4:8] == b"ftyp":
        return "mp4"
    return None


def write(path, meta):
    """把 meta（dict）寫進檔案，回傳 WRITTEN、SIGNED 或 UNSUPPORTED。圖片先寫到暫存檔再換掉原檔；MP4 直接接在檔尾。"""
    path = Path(path)
    payload = json.dumps(meta, ensure_ascii=False, separators=(",", ":")).encode()
    with open(path, "rb") as f:
        kind = kind_of(f.read(16))
    if kind == "mp4":
        return _write_mp4(path, payload)
    if kind not in ("png", "jpeg", "webp"):
        return UNSUPPORTED
    data = path.read_bytes()
    if {"png": _png_signed, "jpeg": _jpeg_signed, "webp": _webp_signed}[kind](data):
        return SIGNED
    data = {"png": _png, "jpeg": _jpeg, "webp": _webp}[kind](data, payload)
    if data is None:
        return UNSUPPORTED
    tmp = path.with_name(path.name + ".meta")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return WRITTEN


def read(path):
    """讀出寫進去的 meta，沒有（或讀不懂）是 None。"""
    try:
        with open(path, "rb") as f:
            kind = kind_of(f.read(16))
            if kind == "mp4":
                size = os.fstat(f.fileno()).st_size
                ours = [b for b in _mp4_boxes(f, size) or [] if b[4] == MP4_UUID]
                if not ours:
                    return None
                start, box_size, header = ours[-1][:3]
                f.seek(start + header + 16)
                payload = f.read(box_size - header - 16)
            elif kind:
                f.seek(0)
                payload = {"png": _png_read, "jpeg": _jpeg_read, "webp": _webp_read}[kind](f.read())
            else:
                return None
        meta = json.loads(payload) if payload else None
    except (ValueError, IndexError, struct.error):
        return None
    return meta if isinstance(meta, dict) and meta.get("app") == KEY else None


# ---------- PNG ----------
def _png_chunks(data):
    """切成 [(類型, 整個 chunk 的 bytes)]，第一個是 IHDR、最後一個是 IEND；結構不對是 None。"""
    if not data.startswith(PNG_SIG):
        return None
    chunks, pos = [], len(PNG_SIG)
    while pos + 12 <= len(data):
        length, ctype = struct.unpack(">I4s", data[pos:pos + 8])
        end = pos + 12 + length
        if end > len(data):
            return None
        chunks.append((ctype, data[pos:end]))
        pos = end
        if ctype == b"IEND":
            break
    if not chunks or chunks[0][0] != b"IHDR" or chunks[-1][0] != b"IEND":
        return None
    return chunks


def _png_signed(data):
    return any(ctype == b"caBX" for ctype, _ in _png_chunks(data) or [])


def _png_ours(ctype, chunk):
    return ctype == b"iTXt" and chunk[8:9 + len(KEY)] == KEY.encode() + b"\0"


def _png(data, payload):
    chunks = _png_chunks(data)
    if chunks is None:
        return None
    # iTXt：關鍵字、\0、不壓縮（0、0）、語言標籤（空）\0、翻譯的關鍵字（空）\0、內容
    body = KEY.encode() + b"\0\0\0\0\0" + payload
    ours = struct.pack(">I", len(body)) + b"iTXt" + body + struct.pack(">I", zlib.crc32(b"iTXt" + body))
    kept = [chunk for ctype, chunk in chunks if not _png_ours(ctype, chunk)]
    return PNG_SIG + kept[0] + ours + b"".join(kept[1:])


def _png_read(data):
    for ctype, chunk in _png_chunks(data) or []:
        if _png_ours(ctype, chunk):
            rest = chunk[8:-4][len(KEY) + 1:]
            if rest[:1] != b"\0":  # 我們不壓縮；壓縮過的就不是我們寫的
                return None
            lang_end = rest.index(b"\0", 2)
            return rest[rest.index(b"\0", lang_end + 1) + 1:]
    return None


# ---------- JPEG ----------
def _jpeg_segments(data, until_scan=False):
    """回傳 (段 [(marker, bytes)], 其餘的 bytes)；結構不對是 None。
    預設只切開頭連續的 APPn、COM（要插入 COM 的位置）；until_scan 為真時一直切到影像資料（SOS）前。"""
    if data[:2] != b"\xff\xd8":
        return None
    segments, pos = [], 2
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            return None
        marker = data[pos + 1]
        if marker == 0xFF:  # 填充用的 0xFF
            pos += 1
            continue
        if marker in (0xDA, 0xD9) or not (until_scan or 0xE0 <= marker <= 0xEF or marker == 0xFE):
            break
        length = struct.unpack(">H", data[pos + 2:pos + 4])[0]
        end = pos + 2 + length
        if length < 2 or end > len(data):
            return None
        segments.append((marker, data[pos:end]))
        pos = end
    return segments, data[pos:]


def _jpeg_signed(data):
    """C2PA 放在 APP11（JUMBF）段裡。結構看不懂（例如段和段中間有多的 byte）時看不出有沒有，當作有，不冒險改。"""
    parsed = _jpeg_segments(data, until_scan=True)
    return parsed is None or any(marker == 0xEB and (b"c2pa" in seg or b"jumb" in seg) for marker, seg in parsed[0])


def _jpeg(data, payload):
    parsed = _jpeg_segments(data)
    if parsed is None:
        return None
    segments, rest = parsed
    parts = [payload[i:i + JPEG_MAX] for i in range(0, len(payload), JPEG_MAX)]
    if len(parts) > 255:
        return None
    ours = b"".join(b"\xff\xfe" + struct.pack(">H", 2 + len(JPEG_TAG) + 2 + len(p)) + JPEG_TAG + bytes([i, len(parts)]) + p
                    for i, p in enumerate(parts))
    kept = b"".join(seg for marker, seg in segments if not (marker == 0xFE and seg[4:8] == JPEG_TAG))
    return b"\xff\xd8" + kept + ours + rest


def _jpeg_read(data):
    parsed = _jpeg_segments(data)
    if parsed is None:
        return None
    found, total = {}, 0
    for marker, seg in parsed[0]:
        if marker == 0xFE and seg[4:8] == JPEG_TAG and len(seg) >= 10:
            found[seg[8]], total = seg[10:], seg[9]
    if not total or sorted(found) != list(range(total)):
        return None
    return b"".join(found[i] for i in range(total))


# ---------- WebP ----------
def _webp_chunks(data):
    if len(data) < 20 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    end = min(len(data), 8 + struct.unpack("<I", data[4:8])[0])
    chunks, pos = [], 12
    while pos + 8 <= end:
        fourcc, size = data[pos:pos + 4], struct.unpack("<I", data[pos + 4:pos + 8])[0]
        body = data[pos + 8:pos + 8 + size]
        if len(body) < size:
            return None
        chunks.append((fourcc, body))
        pos += 8 + size + (size & 1)  # chunk 補齊到偶數長度
    return chunks or None


def _webp_signed(data):
    return any(fourcc == b"C2PA" for fourcc, _ in _webp_chunks(data) or [])


def _webp_canvas(fourcc, body):
    """簡單格式的畫面尺寸和有沒有透明：((寬, 高), 透明)，讀不懂是 None。"""
    if fourcc == b"VP8 " and len(body) >= 10 and body[3:6] == b"\x9d\x01\x2a":
        w, h = struct.unpack("<HH", body[6:10])
        return (w & 0x3FFF, h & 0x3FFF), False
    if fourcc == b"VP8L" and len(body) >= 5 and body[0] == 0x2F:
        bits = struct.unpack("<I", body[1:5])[0]
        return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1), bool(bits >> 28 & 1)
    return None


def _webp(data, payload):
    chunks = _webp_chunks(data)
    if chunks is None:
        return None
    chunks = [c for c in chunks if c[0] != WEBP_CHUNK]
    if chunks[0][0] != b"VP8X":
        if len(chunks) != 1:
            return None
        canvas = _webp_canvas(*chunks[0])
        if not canvas or not all(canvas[0]):
            return None
        (w, h), alpha = canvas
        vp8x = bytes([0x10 if alpha else 0, 0, 0, 0]) + (w - 1).to_bytes(3, "little") + (h - 1).to_bytes(3, "little")
        chunks.insert(0, (b"VP8X", vp8x))
    chunks.append((WEBP_CHUNK, payload))
    body = b"WEBP" + b"".join(fourcc + struct.pack("<I", len(b)) + b + b"\0" * (len(b) & 1) for fourcc, b in chunks)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def _webp_read(data):
    return next((body for fourcc, body in reversed(_webp_chunks(data) or []) if fourcc == WEBP_CHUNK), None)


# ---------- MP4 ----------
def _mp4_boxes(f, size):
    """頂層的 box：[(開始的位置, 大小, 標頭長度, 大小寫成 0（到檔尾）, 標記)]；結構不對是 None。
    標記：uuid box 是它的 UUID，free box 是內容的前 16 bytes（我們寫的是 MP4_UUID），其他是 None。"""
    boxes, pos = [], 0
    while pos + 8 <= size:
        f.seek(pos)
        head = f.read(16)
        box_size, box_type = struct.unpack(">I4s", head[:8])
        header, to_end = 8, box_size == 0
        if box_size == 1:
            if len(head) < 16:
                return None
            box_size, header = struct.unpack(">Q", head[8:16])[0], 16
        elif to_end:
            box_size = size - pos
        if box_size < header or pos + box_size > size:
            return None
        tag = None
        if box_type in (b"uuid", b"free") and box_size >= header + 16:
            f.seek(pos + header)
            tag = f.read(16)
        boxes.append((pos, box_size, header, to_end, tag))
        pos += box_size
    return boxes if pos == size else None


def _write_mp4(path, payload):
    with open(path, "r+b") as f:
        size = os.fstat(f.fileno()).st_size
        boxes = _mp4_boxes(f, size)
        if not boxes:
            return UNSUPPORTED
        for start, box_size, header, _, tag in boxes:
            # 有憑證：要確定它不檢查 free box（exclusions 裡有 CBOR 字串 "/free"）才寫；最後一個 box 寫著「到檔尾」時
            # 要改它的標頭（憑證有檢查）才接得上，也不寫
            if tag == C2PA_UUID:
                if box_size > C2PA_MAX or boxes[-1][3]:
                    return SIGNED
                f.seek(start + header)
                if b"\x65/free" not in f.read(box_size - header):
                    return SIGNED
        if boxes[-1][4] == MP4_UUID and len(boxes) > 1:  # 之前寫過（例如改名前）：截掉再接新的
            size = boxes[-1][0]
            f.truncate(size)
            boxes.pop()
        start, box_size, _, to_end, _ = boxes[-1]
        if to_end:  # 最後一個 box 寫著「到檔尾」：改成實際大小，後面才接得上新的 box
            if box_size > 0xFFFFFFFF:
                return UNSUPPORTED
            f.seek(start)
            f.write(struct.pack(">I", box_size))
        f.seek(size)
        f.write(struct.pack(">I", 8 + 16 + len(payload)) + b"free" + MP4_UUID + payload)
    return WRITTEN
