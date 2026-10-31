# -*- coding: utf-8 -*-
"""Artifact용 조각 index.html → GitHub Pages용 완전한 HTML(docs/).

Artifact는 게시 시점에 <!doctype>·<html>·<head>·<body>와 기본 리셋을 알아서 씌워준다.
그래서 원본 index.html에는 그 태그가 없다. **GitHub Pages는 아무것도 씌워주지 않으므로
그대로 올리면 charset이 없어 한글이 깨지고, viewport가 없어 폰에서 축소되어 보인다.**

원본은 Artifact 배포 경로를 유지해야 하니 건드리지 않고, 여기서 감싸서 docs/에 낸다.
"""
import io
import os
import re
import shutil
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "index.html")
DOCS = os.path.join(HERE, "docs")

# Artifact 런타임이 넣어주던 것과 같은 최소 리셋
RESET = """    html{color-scheme:light dark}
    body{margin:0;font:14px system-ui,-apple-system,sans-serif}
    img{max-width:100%}
    [hidden]{display:none!important}"""


def main():
    frag = io.open(SRC, encoding="utf-8").read()

    m = re.search(r"<title>(.*?)</title>", frag, re.S)
    title = m.group(1).strip() if m else "세계 국기 카드"
    desc = ("세계 197개국 국기를 카드로 넘겨보며 나라 이름을 익히고, "
            "주요 50개국 수도 퀴즈와 랜드마크 퀴즈도 풀어보는 아이용 학습 카드.")

    head_bits, body = [], frag
    # <title>과 <link rel=...>은 head로 옮긴다(조각에서는 순서가 자유롭지만 정식 문서는 아니다)
    for pat in (r"<title>.*?</title>\s*", r"<link\b[^>]*>\s*"):
        for x in re.findall(pat, body, re.S):
            head_bits.append(x.strip())
        body = re.sub(pat, "", body, flags=re.S)

    head = "\n    ".join(head_bits)
    html = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="description" content="{desc}">
<meta name="theme-color" content="#dceef7" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#141d2e" media="(prefers-color-scheme: dark)">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="국기 카드">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="website">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🌍</text></svg>">
    {head}
<style>
{reset}
</style>
</head>
<body>
{body}
</body>
</html>
""".format(desc=desc, title=title, head=head, reset=RESET, body=body.strip())

    os.makedirs(DOCS, exist_ok=True)
    out = os.path.join(DOCS, "index.html")
    # UTF-8 BOM 없이 charset 선언으로 충분하다(서버가 text/html; charset=utf-8로 낸다)
    io.open(out, "w", encoding="utf-8", newline="\n").write(html)
    shutil.copy2(os.path.join(HERE, "flags.js"), os.path.join(DOCS, "flags.js"))

    # 랜드마크 사진 — index.html이 상대경로 landmarks/<code>.webp로 부른다(Artifact도 같은 경로로 올림)
    src_lm, dst_lm = os.path.join(HERE, "landmarks"), os.path.join(DOCS, "landmarks")
    if os.path.isdir(dst_lm):
        shutil.rmtree(dst_lm)
    shutil.copytree(src_lm, dst_lm)
    lm_files = [f for f in os.listdir(dst_lm) if f.endswith(".webp")]
    lm_size = sum(os.path.getsize(os.path.join(dst_lm, f)) for f in lm_files)

    # Jekyll이 밑줄로 시작하는 파일을 숨기는 걸 막는다(지금은 없지만 안전장치)
    io.open(os.path.join(DOCS, ".nojekyll"), "w", encoding="utf-8").write("")

    print("docs/index.html {0:.1f}KB".format(os.path.getsize(out) / 1024))
    print("docs/flags.js   {0:.2f}MB".format(
        os.path.getsize(os.path.join(DOCS, "flags.js")) / 1048576))
    print("docs/landmarks/ {0}장 {1:.2f}MB".format(len(lm_files), lm_size / 1048576))
    for need in ("<!doctype html>", 'charset="utf-8"', "viewport",
                 'src="flags.js"', "</html>"):
        print("  {0} {1}".format("OK  " if need in html else "빠짐", need))
    return 0


if __name__ == "__main__":
    sys.exit(main())
