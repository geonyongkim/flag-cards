# -*- coding: utf-8 -*-
"""랜드마크 퀴즈 사진 수집·검수·압축 도구.

사용법
  python fetch_landmarks.py search [code ...] [--term N] [--page N]  Pexels 검색 → 후보 내려받기
  python fetch_landmarks.py commons <code> "<검색어>"                   Wikimedia Commons 후보 추가
  python fetch_landmarks.py sheet <code> [code ...]                     컨택트시트(후보 격자) 만들기
  python fetch_landmarks.py pick <code> <후보번호>                      채택 → landmarks.json에 출처 기록
  python fetch_landmarks.py build                                       채택 사진 → landmarks/<code>.webp

- Pexels 키는 자랑형_5편/.env의 PEXELS_API_KEY를 **읽기만** 한다. 값은 어디에도 출력·저장하지 않는다.
- 검색 결과는 .landmark_cache/에 캐시해서 같은 검색어로는 API를 다시 부르지 않는다.
- 호출은 최근 1시간 190회 이하. 같은 키를 쓰는 다른 수집기(1번 폴더)의 호출 기록도 **읽기만** 해서 합산한다.
- Commons는 CC0 / PD / CC BY / CC BY-SA만 받는다(NC·ND 제외).
"""
import hashlib
import html
import io
import json
import os
import re
import sys
import time

import requests
from dotenv import dotenv_values
from PIL import Image, ImageDraw, ImageFont, ImageOps

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
LANDMARKS = os.path.join(HERE, "landmarks.json")
OUT_DIR = os.path.join(HERE, "landmarks")
CACHE = os.path.join(HERE, ".landmark_cache")
SEARCH_DIR = os.path.join(CACHE, "search")
CAND_DIR = os.path.join(CACHE, "cand")
THUMB_DIR = os.path.join(CACHE, "thumb")
SHEET_DIR = os.path.join(CACHE, "sheet")
RATE_FILE = os.path.join(CACHE, "rate.json")

ENV_FILE = r"D:\ai-agent\Claude AI\분석_UCSBGz\자랑형_5편\.env"
# 같은 키를 쓰는 기존 수집기의 호출 기록 — 읽기만 한다(시간당 한도는 키 단위라 합산해야 안전)
SHARED_RATE = r"D:\ai-agent\Claude AI\분석_UCSBGz\자랑형_5편\_공용\stock_cache\rate.json"
HOURLY = 190
MAX_CAND = 8
OUT_LONG = 800       # 앱에 넣는 사진의 긴 변
WEBP_Q = 80
UA = "FlagCardsLandmarkFetch/1.0 (https://geonyongkim.github.io/flag-cards/; kids learning app) python-requests"

LICENSE_OK = re.compile(r"^(cc[- ]?by(-sa)?[- ]?\d|cc0|public domain|pd\b|pd-)", re.I)

for d in (SEARCH_DIR, CAND_DIR, THUMB_DIR, SHEET_DIR, OUT_DIR):
    os.makedirs(d, exist_ok=True)


def read_json(path, default):
    try:
        with io.open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path, obj, indent=1):
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent)
    os.replace(tmp, path)


def pexels_key():
    """키는 메모리에만 둔다(환경 변수·파일·로그 어디에도 남기지 않는다)."""
    key = (dotenv_values(ENV_FILE).get("PEXELS_API_KEY") or "").strip()
    if not key:
        raise SystemExit("PEXELS_API_KEY를 읽지 못했습니다(.env 확인)")
    return key


def mask(text, key):
    """혹시 오류 메시지에 키가 섞여 나오면 가린다."""
    return text.replace(key, "****") if key else text


# ── 요청 한도 ──
def rate_slot():
    """API 1회 호출 전에 부른다. 최근 1시간 호출(내 기록 + 공용 기록)이 한도면 기다린다."""
    while True:
        now = time.time()
        mine = [t for t in read_json(RATE_FILE, {"calls": []}).get("calls", []) if now - t < 3600]
        shared = read_json(SHARED_RATE, {"calls": []})
        other = [t for t in shared.get("calls", []) if now - t < 3600]
        calls = sorted(mine + other)
        if len(calls) < HOURLY:
            mine.append(now)
            write_json(RATE_FILE, {"calls": mine})
            return len(calls) + 1
        wait = min(max(calls[0] + 3600 - now, 1), 300)
        print("  [Pexels 한도] {0:.0f}초 대기".format(wait), flush=True)
        time.sleep(wait)


def cache_path(source, query, extra):
    h = hashlib.md5("{0}|{1}|{2}".format(source, query, extra).encode("utf-8")).hexdigest()[:16]
    return os.path.join(SEARCH_DIR, "{0}_{1}.json".format(source, h))


def search_pexels(query, page=1, per_page=15):
    cp = cache_path("pexels", query, "landscape|{0}|{1}".format(page, per_page))
    data = read_json(cp, None)
    if data is not None:
        return data, False
    key = pexels_key()
    params = {"query": query, "orientation": "landscape", "page": page, "per_page": per_page}
    for attempt in range(3):
        n = rate_slot()
        try:
            r = requests.get("https://api.pexels.com/v1/search", params=params,
                             headers={"Authorization": key, "User-Agent": UA}, timeout=30)
        except requests.RequestException as e:
            raise SystemExit("Pexels 요청 실패: " + mask(str(e), key))
        if r.status_code == 429:
            time.sleep(30 * (attempt + 1))
            continue
        if r.status_code != 200:
            raise SystemExit("Pexels 응답 {0}: {1}".format(r.status_code, mask(r.text[:200], key)))
        data = r.json()
        write_json(cp, data)
        print("  (API 호출, 최근 1시간 {0}회)".format(n))
        return data, True
    raise SystemExit("Pexels 429 반복: " + query)


def download(url, dst):
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        return dst
    # Commons 이미지 서버는 연속 요청에 429를 낸다 → 간격을 두고, 걸리면 물러났다 다시
    slow = "wikimedia.org" in url
    for attempt in range(4):
        if slow:
            time.sleep(2 + attempt * 8)
        r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
        if r.status_code != 429:
            break
    r.raise_for_status()
    with open(dst, "wb") as f:
        f.write(r.content)
    return dst


def cands_of(code):
    return read_json(os.path.join(CAND_DIR, code + ".json"), [])


def save_cands(code, cands):
    write_json(os.path.join(CAND_DIR, code + ".json"), cands)


def add_cands(code, new):
    """후보 목록에 중복 없이 붙이고 미리보기를 내려받는다."""
    cands = cands_of(code)
    have = {c["key"] for c in cands}
    added = 0
    for c in new:
        if c["key"] in have:
            continue
        thumb = os.path.join(THUMB_DIR, "{0}_{1}.jpg".format(code, re.sub(r"\W", "_", c["key"])))
        try:
            download(c["thumb"], thumb)
        except requests.RequestException as e:
            print("  미리보기 실패 {0}: {1}".format(c["key"], e))
            continue
        c["thumb_file"] = thumb
        cands.append(c)
        have.add(c["key"])
        added += 1
    save_cands(code, cands)
    return added, len(cands)


def cmd_search(args):
    marks = read_json(LANDMARKS, {})
    term, page = 0, 1
    codes = []
    i = 0
    while i < len(args):
        if args[i] == "--term":
            term = int(args[i + 1]); i += 2
        elif args[i] == "--page":
            page = int(args[i + 1]); i += 2
        elif args[i] == "--q":
            codes.append(("q", args[i + 1])); i += 2
        else:
            codes.append(("c", args[i])); i += 1
    custom = [q for kind, q in codes if kind == "q"]
    targets = [c for kind, c in codes if kind == "c"] or list(marks)
    for code in targets:
        lm = marks[code]
        query = custom[0] if custom else lm["search"][min(term, len(lm["search"]) - 1)]
        data, _ = search_pexels(query, page)
        new = []
        for p in data.get("photos", []):
            if len(new) >= MAX_CAND:
                break
            src = p.get("src") or {}
            new.append({
                "key": "pexels:{0}".format(p["id"]), "source": "Pexels", "photo_id": p["id"],
                "photographer": p.get("photographer", ""),
                "photographer_url": p.get("photographer_url", ""),
                "page_url": p.get("url", ""), "alt": p.get("alt", ""),
                "width": p.get("width"), "height": p.get("height"),
                "thumb": src.get("large"), "full": (src.get("original") or "") + "?auto=compress&cs=tinysrgb&w=1600",
                "license": "Pexels License", "license_url": "https://www.pexels.com/license/",
                "query": query})
        added, total = add_cands(code, new)
        print("{0} [{1}] +{2} → 후보 {3}".format(code, query, added, total))


def search_commons(query, limit=20):
    cp = cache_path("commons", query, str(limit))
    data = read_json(cp, None)
    if data is None:
        params = {"action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
                  "gsrsearch": "filetype:bitmap " + query, "gsrlimit": limit,
                  "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1280}
        r = requests.get("https://commons.wikimedia.org/w/api.php", params=params,
                         headers={"User-Agent": UA}, timeout=30)
        r.raise_for_status()
        data = r.json()
        write_json(cp, data)
    pages = sorted((data.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    out = []
    for p in pages:
        ii = (p.get("imageinfo") or [{}])[0]
        em = ii.get("extmetadata") or {}
        lic = (em.get("LicenseShortName") or {}).get("value", "").strip()
        if not LICENSE_OK.match(lic) or re.search(r"\b(nc|nd)\b", lic, re.I):
            continue
        w, h = ii.get("width") or 0, ii.get("height") or 0
        if w < 1000 or w < h:           # 가로 사진만
            continue
        artist = re.sub(r"<[^>]+>", " ", html.unescape((em.get("Artist") or {}).get("value", "")))
        artist = re.sub(r"\s+", " ", artist).strip()[:80] or "unknown"
        thumb = ii.get("thumburl") or ii.get("url")
        out.append({
            "key": "commons:{0}".format(p.get("pageid")), "source": "Wikimedia Commons",
            "photo_id": p.get("pageid"), "photographer": artist, "photographer_url": "",
            "page_url": ii.get("descriptionurl", ""), "alt": p.get("title", "").replace("File:", ""),
            "width": w, "height": h, "thumb": thumb, "full": thumb,
            "license": lic, "license_url": (em.get("LicenseUrl") or {}).get("value", ""),
            "query": query})
    return out


def cmd_commons(args):
    code, query = args[0], args[1]
    new = search_commons(query)[:MAX_CAND]
    added, total = add_cands(code, new)
    print("{0} [Commons: {1}] +{2} → 후보 {3}".format(code, query, added, total))


def font(size):
    for name in ("malgunbd.ttf", "malgun.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def cmd_sheet(args):
    """후보를 번호와 함께 격자로 붙인다(나라당 4열). 여러 나라를 한 장에 세로로 쌓는다."""
    marks = read_json(LANDMARKS, {})
    tw, th, cols, pad, head = 300, 200, 4, 6, 30
    blocks = []
    for code in args:
        cands = cands_of(code)
        rows = max(1, (len(cands) + cols - 1) // cols)
        blk = Image.new("RGB", (cols * (tw + pad) + pad, head + rows * (th + pad) + pad), "white")
        d = ImageDraw.Draw(blk)
        d.text((pad, 4), "{0} {1}".format(code, marks.get(code, {}).get("en", "")), fill="black", font=font(20))
        for i, c in enumerate(cands):
            try:
                im = Image.open(c["thumb_file"]).convert("RGB")
            except (OSError, KeyError):
                continue
            im = ImageOps.fit(im, (tw, th))
            x, y = pad + (i % cols) * (tw + pad), head + (i // cols) * (th + pad)
            blk.paste(im, (x, y))
            tag = "{0} {1}".format(i, "C" if c["source"] != "Pexels" else "")
            d.rectangle([x, y, x + 46, y + 26], fill="yellow")
            d.text((x + 4, y + 1), tag, fill="black", font=font(20))
        blocks.append(blk)
    if not blocks:
        return
    W = max(b.width for b in blocks)
    sheet = Image.new("RGB", (W, sum(b.height for b in blocks)), "gray")
    y = 0
    for b in blocks:
        sheet.paste(b, (0, y))
        y += b.height
    out = os.path.join(SHEET_DIR, "_".join(args) + ".jpg")
    sheet.save(out, quality=85)
    print(out)


def cmd_pick(args):
    code, idx = args[0], int(args[1])
    c = cands_of(code)[idx]
    marks = read_json(LANDMARKS, {})
    lm = marks[code]
    for k in ("photo_id", "photographer", "photographer_url", "license", "license_url"):
        lm[k] = c.get(k, "")
    lm["source"] = c["source"]
    if c["source"] == "Pexels":
        lm["pexels_url"] = c["page_url"]
        lm.pop("source_url", None)
    else:
        lm["source_url"] = c["page_url"]
        lm.pop("pexels_url", None)
    lm["full"] = c["full"]
    write_pretty(marks)
    print("{0} ← {1} ({2}, {3})".format(code, c["key"], c["photographer"], c["alt"][:60]))


def write_pretty(marks):
    """나라 한 줄씩 — 사람이 읽고 고치기 쉽게."""
    lines = ['  "{0}": {1}'.format(k, json.dumps(v, ensure_ascii=False)) for k, v in marks.items()]
    with io.open(LANDMARKS, "w", encoding="utf-8", newline="\n") as f:
        f.write("{\n" + ",\n".join(lines) + "\n}\n")


def cmd_build(args):
    marks = read_json(LANDMARKS, {})
    total, missing = 0, []
    for code, lm in marks.items():
        if args and code not in args:
            continue
        if not lm.get("full"):
            missing.append(code)
            continue
        raw = os.path.join(CACHE, "full_{0}_{1}.img".format(code, lm["photo_id"]))
        download(lm["full"], raw)
        im = Image.open(raw)
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((OUT_LONG, OUT_LONG), Image.LANCZOS)
        out = os.path.join(OUT_DIR, code + ".webp")
        im.save(out, "WEBP", quality=WEBP_Q, method=6)
        size = os.path.getsize(out)
        total += size
        print("{0} {1}x{2} {3:.0f}KB".format(code, im.width, im.height, size / 1024))
    print("합계 {0:.2f}MB".format(total / 1048576))
    if missing:
        print("미선정: " + ", ".join(missing))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd, args = sys.argv[1], sys.argv[2:]
    {"search": cmd_search, "commons": cmd_commons, "sheet": cmd_sheet,
     "pick": cmd_pick, "build": cmd_build}[cmd](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
