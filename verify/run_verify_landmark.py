# -*- coding: utf-8 -*-
"""랜드마크 퀴즈 검증 — docs/를 정적 서버로 띄우고 Playwright로 실제 화면을 돌린다.

1) 데이터: 50개국(수도 퀴즈와 같은 나라)·랜드마크 이름·출처, 사진 50장 파일 존재 + 브라우저 로딩(naturalWidth>0)
2) 출제 규칙: 단계마다 무작위 100판 — 보기 4개 중복 없음, 정답 포함, 같은 대륙 우선
3) 한 판 자동 플레이: 정답 · 오답 · 복습 · 결과 (스크린샷), 기록 키 분리(flagcards.landmarks)
4) 사진 못 불러올 때 대체 화면, 사진 출처 50줄, 숫자키, 모드 기억, 저장 차단 환경
5) 레이아웃: 폰 세로/가로 · 태블릿 세로/가로 · 다크 (스크린샷), 모드 버튼 한 줄
기존 국기 카드·수도 퀴즈 회귀는 run_verify.py가 맡는다.
"""
import functools
import http.server
import os
import sys
import threading

from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(os.path.dirname(HERE), "docs")
PORT = 8818
URL = "http://127.0.0.1:{0}/index.html".format(PORT)
fails = []


def check(cond, msg):
    print(("  OK  " if cond else "  실패 ") + msg)
    if not cond:
        fails.append(msg)


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve():
    handler = functools.partial(QuietHandler, directory=DOCS)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


SIM_JS = """() => {
  const Q = window.FLAGS.filter(f => f.p && f.l);
  const res = {n: Q.length, capN: window.FLAGS.filter(f => f.p).length,
               noName: Q.filter(f => !f.l.k || !f.l.by || !f.l.u).length,
               dupNames: Q.length - new Set(Q.map(f => f.l.k)).size,
               rounds: 0, questions: 0, bad: [], sameContMiss: 0};
  const groups = {
    easy: f => f.d === 1, all: () => true,
    asia: f => f.t === '아시아' || f.t === '오세아니아', eu: f => f.t === '유럽',
    af: f => f.t === '아프리카', am: f => f.t === '북아메리카' || f.t === '남아메리카'};
  for (const [g, pick] of Object.entries(groups)) {
    const pool = Q.filter(pick);
    for (let r = 0; r < 100; r++) {
      const round = CapQuiz.round(pool, Math.random);
      res.rounds++;
      if (round.length !== Math.min(10, pool.length)) res.bad.push(g + ' 판 길이 ' + round.length);
      if (new Set(round.map(f => f.c)).size !== round.length) res.bad.push(g + ' 판 안 문제 중복');
      for (const q of round) {
        res.questions++;
        const ch = CapQuiz.choices(q, Q, Math.random, 'k');
        const names = ch.map(c => c.k);
        if (ch.length !== 4) res.bad.push(q.c + ' 보기 수 ' + ch.length);
        if (new Set(names).size !== 4) res.bad.push(q.c + ' 보기 중복');
        if (!ch.some(c => c.c === q.c)) res.bad.push(q.c + ' 정답 없음');
        if (ch.some(c => !Q.includes(c))) res.bad.push(q.c + ' 50개국 밖 보기');
        const sameN = Q.filter(f => f.t === q.t && f.c !== q.c).length;
        const got = ch.filter(c => c.c !== q.c && c.t === q.t).length;
        if (got !== Math.min(3, sameN)) res.sameContMiss++;
      }
    }
  }
  res.bad = res.bad.slice(0, 10);
  return res;
}"""

# 50장 모두 실제로 브라우저에서 디코딩되는지 — 페이지와 같은 상대경로로 부른다
IMG_JS = """async () => {
  const Q = window.FLAGS.filter(f => f.l);
  const out = await Promise.all(Q.map(f => new Promise(ok => {
    const im = new Image();
    im.onload = () => ok({c: f.c, w: im.naturalWidth, h: im.naturalHeight});
    im.onerror = () => ok({c: f.c, w: 0, h: 0});
    im.src = 'landmarks/' + f.c + '.webp';
  })));
  return out;
}"""


def answer_code(page):
    """화면의 사진 주소(landmarks/<code>.webp)로 정답 나라 코드를 찾는다."""
    return page.evaluate("""() => document.getElementById('limg')
        .getAttribute('src').match(/landmarks\\/(\\w+)\\.webp/)[1]""")


def wait_ready(page):
    page.wait_for_selector(".opt:not([disabled])")
    page.wait_for_function("document.getElementById('limg').complete")


def play_round(page, shot):
    """'전체' 한 판: 2번째 문제만 틀리고 나머지는 맞힌다."""
    page.click("#lq-all")
    for i in range(10):
        wait_ready(page)
        code = answer_code(page)
        if i == 1:
            page.locator('.opt:not([data-code="{0}"])'.format(code)).first.click()
            page.wait_for_selector("#qnext:not([hidden])")
            tip = page.inner_text("#qtip")
            check("괜찮아요" in tip and "에 있어요" in tip, "오답 시 부드러운 안내: " + tip)
            check(page.locator(".opt.ok").get_attribute("data-code") == code, "오답 시 정답 보기 강조")
            check(page.locator("#qtip .tflag svg").count() == 1, "안내 문구에 국기 SVG")
            page.screenshot(path=os.path.join(HERE, shot + "_2_wrong.png"))
            page.click("#qnext")
        else:
            page.click('.opt[data-code="{0}"]'.format(code))
            if i == 0:
                page.wait_for_timeout(350)
                tip = page.inner_text("#qtip")
                cap = page.inner_text("#lcap")
                check(tip.startswith("딩동댕!") and "에 있어요" in tip, "정답 칭찬 + 위치: " + tip)
                check(not page.is_hidden("#lcap") and page.locator("#lcap .tflag svg").count() == 1,
                      "사진 위 이름표(국기+이름): " + cap)
                page.screenshot(path=os.path.join(HERE, shot + "_1_correct.png"))
            page.wait_for_function("document.getElementById('qtip').textContent === ''"
                                   " || !document.getElementById('qres').hidden", timeout=6000)
    wait_ready(page)
    check(page.inner_text("#qask").startswith("한 번 더"), "틀린 나라 복습 출제")
    check(page.inner_text("#count").startswith("복습"), "복습 진행 표시")
    page.screenshot(path=os.path.join(HERE, shot + "_3_review.png"))
    page.click('.opt[data-code="{0}"]'.format(answer_code(page)))
    page.wait_for_selector("#qres:not([hidden])", timeout=6000)
    txt = page.inner_text("#resText")
    check("10문제 중 9개" in txt and "1개 더" in txt, "결과 요약: " + txt)
    check(page.locator("#resStars span:not(.off)").count() == 9, "결과 별 9개")
    page.screenshot(path=os.path.join(HERE, shot + "_4_result.png"))


def modes_one_row(page):
    return page.evaluate("""() => {
      const t = [...document.querySelectorAll('.mode')].map(b => Math.round(b.getBoundingClientRect().top));
      return new Set(t).size === 1;
    }""")


def main():
    srv = serve()
    n_files = len([f for f in os.listdir(os.path.join(DOCS, "landmarks")) if f.endswith(".webp")])
    size = sum(os.path.getsize(os.path.join(DOCS, "landmarks", f))
               for f in os.listdir(os.path.join(DOCS, "landmarks")))
    with sync_playwright() as p:
        br = p.chromium.launch()

        # ── 태블릿 가로 + 라이트 ──
        ctx = br.new_context(viewport={"width": 1280, "height": 800}, color_scheme="light")
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(URL)
        page.wait_for_selector("#flagbox svg")

        print("[데이터 · 사진]")
        r = page.evaluate(SIM_JS)
        check(r["n"] == 50 and r["capN"] == 50, "랜드마크 {0}개국 (수도 퀴즈 {1})".format(r["n"], r["capN"]))
        check(r["noName"] == 0 and r["dupNames"] == 0,
              "이름·출처 빠짐 {0} / 이름 중복 {1}".format(r["noName"], r["dupNames"]))
        check(n_files == 50, "docs/landmarks 파일 {0}장, {1:.2f}MB".format(n_files, size / 1048576))
        imgs = page.evaluate(IMG_JS)
        bad = [x["c"] for x in imgs if x["w"] <= 0]
        check(len(imgs) == 50 and not bad, "브라우저 로딩 성공 {0}/50 (naturalWidth>0) 실패 {1}".format(
            len(imgs) - len(bad), bad))
        check(all(max(x["w"], x["h"]) == 800 for x in imgs), "모두 긴 변 800px")

        print("[출제 규칙 · 100판 시뮬레이션]")
        check(not r["bad"], "{0}판 {1}문제 보기 중복·정답 누락 등 위반 {2}".format(
            r["rounds"], r["questions"], r["bad"] or 0))
        check(r["sameContMiss"] == 0, "같은 대륙 우선 위반 {0}".format(r["sameContMiss"]))

        print("[랜드마크 한 판 — 태블릿 가로]")
        cap_before = page.evaluate("localStorage.getItem('flagcards.capitals')")
        page.click("#modeLand")
        check(page.get_attribute("#modeLand", "aria-pressed") == "true", "랜드마크 모드 선택됨")
        chips = page.eval_on_selector_all("#levels .chip", "e => e.map(x => x.textContent)")
        check(chips == ["쉬워요 30", "전체 50", "아시아·오세아니아 16", "유럽 16",
                        "아프리카 8", "아메리카 10"], "단계 " + " / ".join(chips))
        check(page.inner_text("#qask") == "이 랜드마크는 어느 나라에 있을까요?", "질문 문구")
        check(page.is_hidden("#qflag") and page.is_hidden("#qname"), "국기·나라 이름 숨김(정답 힌트 없음)")
        wait_ready(page)
        h = page.eval_on_selector_all(".opt, .mode, #qsound, #credits summary",
                                      "e => Math.min(...e.map(x => x.offsetHeight))")
        check(h >= 56, "터치 타깃 최소 높이 {0}px".format(h))
        page.screenshot(path=os.path.join(HERE, "L0_tablet_landscape.png"))
        play_round(page, "L1_land")
        st = page.evaluate("JSON.parse(localStorage.getItem('flagcards.landmarks'))")
        check(st["plays"] == 1 and st["best"] == 9 and len(st["got"]) == 10,
              "기록 저장 plays={0} best={1} got={2}".format(st["plays"], st["best"], len(st["got"])))
        check(page.evaluate("localStorage.getItem('flagcards.capitals')") == cap_before,
              "수도 퀴즈 기록과 분리(capitals 키 변화 없음)")
        check(page.inner_text("#starIcon") == "📸" and page.inner_text("#starNum") == "10", "머리 📸 10")
        page.click("#qagain")
        check(page.inner_text("#count") == "1 / 10", "다시 하기 → 새 판")
        page.click("#lq-af")
        check(page.inner_text("#count") == "1 / 8", "아프리카 8문제")
        page.keyboard.press("2")
        check(page.locator(".opt[disabled]").count() == 4, "숫자키 2로 보기 선택")

        print("[사진 출처]")
        page.click("#credits summary")
        page.wait_for_selector(".cpanel", state="visible")
        n = page.locator("#creditList li").count()
        links = page.locator("#creditList a").count()
        check(n == 50 and links >= 100, "출처 {0}줄, 링크 {1}개".format(n, links))
        commons = page.locator("#creditList li", has_text="Wikimedia Commons").count()
        check(commons == page.evaluate("FLAGS.filter(f => f.l && f.l.s !== 'Pexels').length"),
              "Commons 사진 {0}장은 라이선스 표기".format(commons))
        page.screenshot(path=os.path.join(HERE, "L2_credits.png"), full_page=True)
        page.click("#credits summary")

        print("[모드 전환 · 기억]")
        page.reload()
        page.wait_for_selector(".opt")
        check(page.get_attribute("#modeLand", "aria-pressed") == "true", "다시 열면 랜드마크 모드 유지")
        page.click("#modeQuiz")
        check(not page.is_hidden("#qflag") and page.is_hidden("#lphoto") and page.is_hidden("#credits"),
              "수도 퀴즈로 바꾸면 국기 보이고 사진·출처 숨김")
        check(page.locator("#lv-all, #qv-all").count() == 1 and page.inner_text("#starIcon") == "🏆",
              "수도 퀴즈 칩·트로피")
        page.click("#modeCard")
        check(not page.is_hidden("#card") and page.is_hidden("#qstage"), "국기 카드 복귀")
        check(not errors, "페이지 오류 없음 " + str(errors[:3]))
        ctx.close()

        print("[사진 못 불러올 때]")
        ctx = br.new_context(viewport={"width": 390, "height": 844})
        ctx.route("**/landmarks/*.webp", lambda route: route.abort())
        page = ctx.new_page()
        page.goto(URL)
        page.click("#modeLand")
        page.wait_for_selector("#lfall:not([hidden])", timeout=5000)
        name = page.inner_text("#lfName")
        code = page.evaluate("""() => document.getElementById('limg').getAttribute('src')
            .match(/landmarks\\/(\\w+)\\.webp/)[1]""")
        want = page.evaluate("c => FLAGS.find(f => f.c === c).l.k", code)
        check(name == want and page.is_hidden("#limg"), "대체 화면: 이모지 + '{0}'".format(name))
        page.screenshot(path=os.path.join(HERE, "L3_fallback.png"))
        page.click('.opt[data-code="{0}"]'.format(code))
        check("딩동댕" in page.inner_text("#qtip"), "사진 없어도 퀴즈 진행")
        ctx.close()

        # ── 레이아웃: 다크 폰 세로 / 폰 가로 / 태블릿 세로, 라이트 폰 세로 ──
        for name, vp, scheme in (("dark_phone_portrait", (390, 844), "dark"),
                                 ("dark_phone_landscape", (844, 390), "dark"),
                                 ("dark_tablet_portrait", (820, 1180), "dark"),
                                 ("light_phone_portrait", (390, 844), "light"),
                                 ("light_small_phone", (360, 740), "light")):
            print("[" + name + "]")
            ctx = br.new_context(viewport={"width": vp[0], "height": vp[1]},
                                 color_scheme=scheme, has_touch=True)
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(URL)
            page.click("#modeLand")
            wait_ready(page)
            sw = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            check(sw <= 0, "가로 스크롤 없음 ({0})".format(sw))
            check(modes_one_row(page), "모드 버튼 3개 한 줄")
            over = page.evaluate("""() => [...document.querySelectorAll('.mode')]
                .filter(b => b.scrollWidth > b.clientWidth + 1).length""")
            check(over == 0, "모드 버튼 글자 넘침 없음 ({0})".format(over))
            if "landscape" in name:
                sh = page.evaluate("document.documentElement.scrollHeight - innerHeight")
                check(sh <= 0, "폰 가로: 세로 스크롤 없이 한 화면 ({0})".format(sh))
                # 가장 긴 나라 이름 4개가 한꺼번에 보기로 나와도 넘치지 않는지(최악의 경우)
                sh2 = page.evaluate("""() => {
                  const names = FLAGS.filter(f => f.l).map(f => f.k).sort((a, b) => b.length - a.length);
                  [...document.querySelectorAll('.opt')].forEach((b, i) => b.textContent = names[i]);
                  return document.documentElement.scrollHeight - innerHeight;
                }""")
                check(sh2 <= 0, "폰 가로: 가장 긴 나라 이름 4개여도 한 화면 ({0})".format(sh2))
                page.screenshot(path=os.path.join(HERE, "L4_dark_phone_landscape_longnames.png"))
            else:
                mh = page.eval_on_selector_all(".opt, .mode",
                                               "e => Math.min(...e.map(x => x.getBoundingClientRect().height))")
                check(mh >= 56, "버튼 최소 높이 {0:.0f}px".format(mh))
            ph = page.evaluate("document.getElementById('lphoto').getBoundingClientRect().height")
            check(ph >= 150, "사진 높이 {0:.0f}px".format(ph))
            if scheme == "dark":
                bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
                check(bg == "rgb(20, 29, 46)", "다크 배경 " + bg)
            page.wait_for_timeout(300)   # 모드 버튼 색 전환(.12s)이 끝난 뒤 찍는다
            page.screenshot(path=os.path.join(HERE, "L4_" + name + ".png"))
            if name == "dark_phone_portrait":
                page.locator('.opt:not([data-code="{0}"])'.format(answer_code(page))).first.tap()
                page.wait_for_timeout(350)
                page.screenshot(path=os.path.join(HERE, "L4_dark_phone_wrong.png"))
            check(not errors, "페이지 오류 없음")
            ctx.close()

        print("[저장 차단 환경]")
        ctx = br.new_context(viewport={"width": 390, "height": 844})
        ctx.add_init_script("""Object.defineProperty(window, 'localStorage',
            {get(){ throw new Error('blocked'); }});""")
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(URL)
        page.click("#modeLand")
        for _ in range(10):
            page.wait_for_selector(".opt:not([disabled])")
            page.locator('.opt:not([data-code="{0}"])'.format(answer_code(page))).first.click()
            page.click("#qnext")
        for _ in range(10):
            page.wait_for_selector(".opt:not([disabled])")
            page.click('.opt[data-code="{0}"]'.format(answer_code(page)))
            page.wait_for_timeout(2300)
        check(not page.is_hidden("#qres"), "저장 막혀도 한 판 끝까지 진행(전부 틀림→복습 10)")
        page.screenshot(path=os.path.join(HERE, "L5_phone_result.png"))
        check(not errors, "페이지 오류 없음 " + str(errors[:3]))
        ctx.close()
        br.close()
    srv.shutdown()
    print("\n결과: " + ("모두 통과" if not fails else "실패 {0}건".format(len(fails))))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
