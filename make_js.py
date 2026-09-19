# -*- coding: utf-8 -*-
"""flags.json → flags.js (window.FLAGS).

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


def main():
    data = json.load(io.open(os.path.join(HERE, "flags.json"), encoding="utf-8"))
    out = [{"c": d["code"], "k": d["ko"], "e": d["en"],
            "t": d["cont"], "d": d["tier"], "s": slim(d["svg"])}
           for d in data]
    body = "window.FLAGS=" + json.dumps(out, ensure_ascii=False,
                                        separators=(",", ":")) + ";"
    path = os.path.join(HERE, "flags.js")
    io.open(path, "w", encoding="utf-8").write(body)
    print("flags.js {0:.2f}MB / {1}개국".format(len(body.encode()) / 1048576, len(out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
