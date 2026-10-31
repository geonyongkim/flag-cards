# -*- coding: utf-8 -*-
"""수도 퀴즈 동작 검증 — docs/를 정적 서버로 띄우고 Playwright로 실제 화면을 돌린다.

1) 데이터: 퀴즈 50개국 수도 존재·빈 문자열 없음·수도명 중복 없음
2) 출제 규칙: 무작위 100판(단계마다) 시뮬레이션 — 보기 4개 중복 없음, 정답 포함, 같은 대륙 우선
3) 한 판 자동 플레이: 정답 클릭 · 오답 클릭 · 복습 · 결과 화면 (스크린샷)
4) 카드 모드 회귀, 다크/가로/폰 레이아웃, 키보드(숫자키), 저장 차단 환경
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
PORT = 8817
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
  const Q = window.FLAGS.filter(f => f.p);
  const caps = Q.map(f => f.p);
  const res = {n: Q.length, empty: Q.filter(f => !f.p.trim()).length,
               dupCaps: caps.length - new Set(caps).size, rounds: 0, questions: 0,
               bad: [], sameContMiss: 0};
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
        const ch = CapQuiz.choices(q, Q, Math.random);
        const names = ch.map(c => c.p);
        if (ch.length !== 4) res.bad.push(q.c + ' 보기 수 ' + ch.length);
        if (new Set(names).size !== 4) res.bad.push(q.c + ' 보기 중복');
        if (!ch.some(c => c.c === q.c)) res.bad.push(q.c + ' 정답 없음');
        if (ch.some(c => !c.p)) res.bad.push(q.c + ' 빈 보기');
        if (ch.some(c => !Q.includes(c))) res.bad.push(q.c + ' 50개국 밖 보기');
        // 같은 대륙 나라가 3개 이상이면 오답 3개 모두 같은 대륙이어야 한다
        const sameN = Q.filter(f => f.t === q.t && f.c !== q.c).length;
        const got = ch.filter(c => c.c !== q.c && c.t === q.t).length;
        if (got !== Math.min(3, sameN)) res.sameContMiss++;
      }
    }
  }
  res.bad = res.bad.slice(0, 10);
  return res;
}"""


def answer_of(page):
    """화면의 나라 이름으로 정답 수도를 찾는다."""
    return page.evaluate("""() => {
      const k = document.getElementById('qname').textContent;
      return window.FLAGS.find(f => f.k === k).p;
    }""")


def play_round(page, shot):
    """'전체' 한 판: 2번째 문제만 틀리고 나머지는 맞힌다."""
    page.click("#qv-all")
    for i in range(10):
        page.wait_for_selector(".opt:not([disabled])")
        ans = answer_of(page)
        if i == 1:
            wrong = page.locator(".opt").filter(has_not_text=ans).first
            wrong.click()
            page.wait_for_selector("#qnext:not([hidden])")
            check("괜찮아요" in page.inner_text("#qtip"), "오답 시 부드러운 안내 문구")
            check(page.locator(".opt.ok").inner_text().startswith(ans), "오답 시 정답 보기 강조")
            page.screenshot(path=os.path.join(HERE, shot + "_2_wrong.png"))
            page.click("#qnext")
        else:
            page.locator(".opt", has_text=ans).first.click()
            if i == 0:
                page.wait_for_timeout(250)
                check("딩동댕" in page.inner_text("#qtip"), "정답 시 칭찬 문구")
                page.screenshot(path=os.path.join(HERE, shot + "_1_correct.png"))
            page.wait_for_function("document.getElementById('qtip').textContent === ''"
                                   " || !document.getElementById('qres').hidden")
    # 복습 문제(틀린 1개)
    page.wait_for_selector(".opt:not([disabled])")
    check("한 번 더" in page.inner_text("#qask"), "틀린 나라 복습 출제")
    check(page.inner_text("#count").startswith("복습"), "복습 진행 표시")
    page.screenshot(path=os.path.join(HERE, shot + "_3_review.png"))
    page.locator(".opt", has_text=answer_of(page)).first.click()
    page.wait_for_selector("#qres:not([hidden])", timeout=5000)
    txt = page.inner_text("#resText")
    check("10문제 중 9개" in txt and "1개 더" in txt, "결과 요약: " + txt)
    check(page.locator("#resStars span:not(.off)").count() == 9, "결과 별 9개")
    page.screenshot(path=os.path.join(HERE, shot + "_4_result.png"))


def main():
    srv = serve()
    with sync_playwright() as p:
        br = p.chromium.launch()

        # ── 태블릿 가로 + 라이트 ──
        ctx = br.new_context(viewport={"width": 1280, "height": 800}, color_scheme="light")
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(URL)
        page.wait_for_selector("#flagbox svg")

        print("[카드 모드 회귀]")
        check(page.inner_text("#count") == "1 / 30", "카드 첫 화면 1 / 30")
        page.click("#card")
        check(page.inner_text("#starNum") == "1", "카드 뒤집으면 별 1")
        page.click("#next")
        check(page.inner_text("#count") == "2 / 30", "다음 나라")
        page.click("#lv-all")
        check(page.inner_text("#count") == "1 / 197", "전부 197")
        page.screenshot(path=os.path.join(HERE, "0_card_landscape.png"))

        print("[데이터 · 100판 시뮬레이션]")
        page.click("#modeQuiz")
        r = page.evaluate(SIM_JS)
        check(r["n"] == 50, "퀴즈 나라 {0}개".format(r["n"]))
        check(r["empty"] == 0 and r["dupCaps"] == 0, "수도 빈 값 {0} / 중복 {1}".format(
            r["empty"], r["dupCaps"]))
        check(not r["bad"], "{0}판 {1}문제 규칙 위반 {2}".format(
            r["rounds"], r["questions"], r["bad"] or 0))
        check(r["sameContMiss"] == 0, "같은 대륙 우선 위반 {0}".format(r["sameContMiss"]))

        print("[퀴즈 한 판 — 가로]")
        chips = page.eval_on_selector_all("#levels .chip", "e => e.map(x => x.textContent)")
        check(chips == ["쉬워요 30", "전체 50", "아시아·오세아니아 16", "유럽 16",
                        "아프리카 8", "아메리카 10"], "퀴즈 단계 " + " / ".join(chips))
        h = page.eval_on_selector_all(".opt, .mode, #qsound",
                                      "e => Math.min(...e.map(x => x.getBoundingClientRect().height))")
        check(h >= 56, "터치 타깃 최소 높이 {0:.0f}px".format(h))
        page.screenshot(path=os.path.join(HERE, "1_quiz_landscape.png"))
        play_round(page, "2_land")
        st = page.evaluate("JSON.parse(localStorage.getItem('flagcards.capitals'))")
        check(st["plays"] == 1 and st["best"] == 9 and len(st["got"]) == 10,
              "기록 저장 plays={0} best={1} got={2}".format(st["plays"], st["best"], len(st["got"])))
        check(page.inner_text("#starNum") == "10", "머리 트로피 수 10")
        page.click("#qagain")
        check(page.inner_text("#count") == "1 / 10", "다시 하기 → 새 판")
        page.click("#qv-af")
        check(page.inner_text("#count") == "1 / 8", "아프리카 8문제")

        print("[키보드]")
        page.keyboard.press("1")
        check(page.locator(".opt[disabled]").count() == 4, "숫자키 1로 보기 선택")
        page.click("#modeCard")
        check(not page.is_hidden("#card") and page.inner_text("#starNum") == "1",
              "카드 모드 복귀 · 별 보존")
        check(not errors, "페이지 오류 없음 " + str(errors[:3]))
        ctx.close()

        # ── 다크 · 폰 세로 / 폰 가로 / 태블릿 세로 ──
        for name, vp in (("phone_portrait", (390, 844)), ("phone_landscape", (844, 390)),
                         ("tablet_portrait", (820, 1180))):
            print("[다크 " + name + "]")
            ctx = br.new_context(viewport={"width": vp[0], "height": vp[1]},
                                 color_scheme="dark", has_touch=True)
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(URL)
            page.click("#modeQuiz")
            page.wait_for_selector(".opt")
            sw = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            check(sw <= 0, "가로 스크롤 없음 ({0})".format(sw))
            bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
            check(bg == "rgb(20, 29, 46)", "다크 배경 " + bg)
            if name == "phone_landscape":
                sh = page.evaluate("document.documentElement.scrollHeight - innerHeight")
                check(sh <= 0, "폰 가로: 세로 스크롤 없이 한 화면 ({0})".format(sh))
            page.wait_for_timeout(300)
            page.screenshot(path=os.path.join(HERE, "3_dark_" + name + ".png"))
            if name == "phone_portrait":
                page.locator(".opt").filter(has_not_text=answer_of(page)).first.tap()
                page.screenshot(path=os.path.join(HERE, "3_dark_phone_wrong.png"))
            check(not errors, "페이지 오류 없음")
            ctx.close()

        # ── 저장 차단(localStorage가 예외를 던지는 환경) ──
        print("[저장 차단 환경]")
        ctx = br.new_context(viewport={"width": 390, "height": 844})
        ctx.add_init_script("""Object.defineProperty(window, 'localStorage',
            {get(){ throw new Error('blocked'); }});""")
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(URL)
        page.click("#modeQuiz")
        for _ in range(10):
            page.wait_for_selector(".opt:not([disabled])")
            page.locator(".opt").filter(has_not_text=answer_of(page)).first.click()
            page.click("#qnext")
        for _ in range(10):
            page.wait_for_selector(".opt:not([disabled])")
            page.locator(".opt", has_text=answer_of(page)).first.click()
            page.wait_for_timeout(1500)
        check(not page.is_hidden("#qres"), "저장 막혀도 한 판 끝까지 진행(전부 틀림→복습 10)")
        check(not errors, "페이지 오류 없음 " + str(errors[:3]))
        ctx.close()
        br.close()
    srv.shutdown()
    print("\n결과: " + ("모두 통과" if not fails else "실패 {0}건".format(len(fails))))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
