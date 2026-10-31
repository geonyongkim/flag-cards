# -*- coding: utf-8 -*-
"""flags.json + capitals.json + landmarks.json → flags.js (window.FLAGS).

SVG를 그대로 인라인해서 쓴다. 외부 이미지는 Artifact CSP가 막으므로
페이지와 함께 올라가야 하고, <script>는 확실히 로드되는 경로다.
"""
import io
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))


def slim(svg):
    """카드에 맞게 정리 — 크기는 CSS가 정하되 비율은 viewBox가 지키게 한다.

    받아온 SVG의 절반쯤(98개)은 **viewBox 없이 width/height만** 갖고 있다.
    그 둘을 지우면 크기 기준이 사라져 CSS의 100%가 그대로 먹혀 국기가 확대되고 잘린다.
    그래서 지우기 전에 width/height로 viewBox를 만들어 넣는다.

    또한 치환은 **여는 <svg> 태그 안에서만** 한다. 문서 전체에서 앞 두 개를 지우면
    svg 태그에 그 속성이 없는 파일은 내부 도형의 width/height가 지워져 그림이 깨진다.
    """
    svg = re.sub(r"<\?xml[^>]*\?>", "", svg)
    svg = re.sub(r"<!--.*?-->", "", svg, flags=re.S)

    m = re.match(r"\s*<svg\b([^>]*)>", svg)
    if m:
        attrs = m.group(1)
        w = re.search(r'\bwidth="([\d.]+)[a-z]*"', attrs)
        h = re.search(r'\bheight="([\d.]+)[a-z]*"', attrs)
        has_vb = "viewBox" in attrs
        new = re.sub(r'\s*\bwidth="[^"]*"', "", attrs)
        new = re.sub(r'\s*\bheight="[^"]*"', "", new)
        if not has_vb and w and h:
            new += ' viewBox="0 0 {0} {1}"'.format(w.group(1), h.group(1))
        # 비율 유지를 못박는다(기본값이지만 파일이 다른 값을 들고 오는 경우가 있다)
        if "preserveAspectRatio" not in new:
            new += ' preserveAspectRatio="xMidYMid meet"'
        svg = svg[:m.start()] + "<svg" + new + ">" + svg[m.end():]

    svg = re.sub(r">\s+<", "><", svg)
    return svg.strip()


QUIZ_SIZE = 50  # 수도 퀴즈 대상 = 주요 50개국(선정 기준은 README)


def load_capitals(codes):
    """capitals.json(code → {ko, en})을 읽고 flags.json과 맞는지 검증한다.

    퀴즈 대상은 capitals.json에 있는 나라 = 정확히 50개국.
    - 모든 코드가 flags.json에 있어야 한다(오타·초과 0개)
    - 한국어 수도명은 비어 있으면 안 되고, 서로 겹치면 안 된다(4지선다 보기 중복 방지)
    하나라도 어긋나면 flags.js를 만들지 않고 멈춘다.
    """
    caps = json.load(io.open(os.path.join(HERE, "capitals.json"), encoding="utf-8"))
    errors = []
    extra = sorted(set(caps) - set(codes))
    if extra:
        errors.append("flags.json에 없는 코드: " + ", ".join(extra))
    if len(caps) != QUIZ_SIZE:
        errors.append("퀴즈 나라 수 {0}개 (기대 {1}개)".format(len(caps), QUIZ_SIZE))
    names = {}
    for code, v in caps.items():
        ko = (v.get("ko") or "").strip()
        if not ko:
            errors.append(code + ": 한국어 수도명 비어 있음")
        elif ko in names:
            errors.append("수도명 중복: {0} ({1}, {2})".format(ko, names[ko], code))
        names[ko] = code
    if errors:
        raise SystemExit("capitals.json 검증 실패\n  " + "\n  ".join(errors))
    return caps


LICENSE_OK = ("Pexels License", "CC0", "Public domain", "CC BY ", "CC BY-SA ")


def load_landmarks(caps):
    """landmarks.json(code → 랜드마크·사진 출처)을 읽고 수도 퀴즈 50개국과 맞는지 검증한다.

    - 나라 목록이 capitals.json과 **정확히 같아야** 한다(퀴즈 대상이 같다)
    - 랜드마크 이름은 비어 있거나 겹치면 안 된다
    - 사진 파일 landmarks/<code>.webp가 있어야 하고, 출처(촬영자·링크)와 허용 라이선스가 있어야 한다
    """
    marks = json.load(io.open(os.path.join(HERE, "landmarks.json"), encoding="utf-8"))
    errors = []
    if set(marks) != set(caps):
        errors.append("capitals.json과 나라가 다름: 빠짐 {0} / 남음 {1}".format(
            sorted(set(caps) - set(marks)), sorted(set(marks) - set(caps))))
    names = {}
    for code, v in marks.items():
        ko = (v.get("ko") or "").strip()
        if not ko:
            errors.append(code + ": 랜드마크 이름 비어 있음")
        elif ko in names:
            errors.append("랜드마크 이름 중복: {0} ({1}, {2})".format(ko, names[ko], code))
        names[ko] = code
        if not os.path.isfile(os.path.join(HERE, "landmarks", code + ".webp")):
            errors.append(code + ": landmarks/{0}.webp 없음".format(code))
        if not v.get("photographer") or not (v.get("pexels_url") or v.get("source_url")):
            errors.append(code + ": 사진 출처(촬영자·링크) 없음")
        lic = v.get("license") or ""
        if not any(lic == x or lic.startswith(x) for x in LICENSE_OK):
            errors.append(code + ": 허용되지 않은 라이선스 " + lic)
    if errors:
        raise SystemExit("landmarks.json 검증 실패\n  " + "\n  ".join(errors))
    return marks


def main():
    data = json.load(io.open(os.path.join(HERE, "flags.json"), encoding="utf-8"))
    caps = load_capitals([d["code"] for d in data])
    marks = load_landmarks(caps)
    out = []
    for d in data:
        item = {"c": d["code"], "k": d["ko"], "e": d["en"],
                "t": d["cont"], "d": d["tier"], "s": slim(d["svg"])}
        cap = caps.get(d["code"])
        if cap:
            # 퀴즈 대상 나라만 수도를 붙인다(p=한국어, pe=영어) — 수 KB만 늘어난다
            item["p"] = cap["ko"].strip()
            item["pe"] = (cap.get("en") or "").strip()
        lm = marks.get(d["code"])
        if lm:
            # 랜드마크 퀴즈용 — 사진은 flags.js에 넣지 않고 landmarks/<code>.webp를 따로 부른다
            item["l"] = {"k": lm["ko"].strip(), "e": lm["en"], "m": lm.get("emoji", "📍"),
                         "by": lm["photographer"], "bu": lm.get("photographer_url", ""),
                         "u": lm.get("pexels_url") or lm.get("source_url"),
                         "s": lm.get("source", "Pexels"), "li": lm.get("license", ""),
                         "lu": lm.get("license_url", "")}
        out.append(item)
    body = "window.FLAGS=" + json.dumps(out, ensure_ascii=False,
                                        separators=(",", ":")) + ";"
    path = os.path.join(HERE, "flags.js")
    io.open(path, "w", encoding="utf-8").write(body)
    print("flags.js {0:.2f}MB / {1}개국 / 수도 퀴즈 {2}개국 / 랜드마크 {3}개국".format(
        len(body.encode()) / 1048576, len(out), len(caps), len(marks)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
