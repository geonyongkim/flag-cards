# 세계 국기 카드

여섯 살 아이가 나라 이름을 익히도록 만든 국기 학습 카드입니다.
카드를 누르면 나라 이름이 나오고, 한 번 더 누르면 다음 나라로 넘어갑니다.

**👉 [바로 열기](https://geonyongkim.github.io/flag-cards/)**

## 무엇이 들어 있나

- 독립국 **197개국** 국기. 벡터(SVG)라 화면을 키워도 깨지지 않습니다
- 단계 선택 — 쉬워요 30 / 보통 70 / 전부 197, 그리고 대륙별 6가지
- "쉬워요"는 대한민국부터 아이에게 익숙한 순서로 나옵니다
- 처음 본 나라마다 별이 쌓입니다(브라우저에 저장되어 다시 열어도 남습니다)
- 태블릿을 눕히면 왼쪽 카드 · 오른쪽 조작부 2단으로 바뀝니다
- 어두운 곳에서는 화면이 어두운 색으로 알아서 바뀝니다

설치할 것도, 인터넷 연결 후 따로 받아올 것도 없습니다. 국기는 전부 페이지 안에 들어 있습니다.

## 파일

| 파일 | 하는 일 |
|---|---|
| `index.html` | 페이지 본체. **Claude Artifact용 조각이라 `<head>`·`<body>`가 없습니다** |
| `flags.js` | 197개국 데이터(이름·대륙·난이도·SVG), 약 2.8MB |
| `docs/` | GitHub Pages가 서비스하는 폴더. `build_pages.py`가 만듭니다 |
| `build_data.py` | flagcdn에서 국기를 받아 `flags.json`을 만듭니다 |
| `make_js.py` | `flags.json` → `flags.js` |
| `build_pages.py` | `index.html`(조각) → `docs/index.html`(완전한 HTML) |

## 고칠 때

```bash
# 나라 목록이나 난이도를 바꾼 경우
python build_data.py     # 국기 내려받기 (인터넷 필요)
python make_js.py        # flags.js 다시 만들기

# 화면을 고친 경우
python build_pages.py    # docs/ 갱신
git add -A && git commit -m "..." && git push
```

`index.html`을 직접 고치고 **`build_pages.py`를 돌리지 않으면 배포 페이지는 그대로입니다.**

## 알아둘 점

- `index.html`에는 `<!doctype>`·`<head>`·`<body>`가 없습니다. Claude Artifact가 게시할 때
  자동으로 씌워주기 때문입니다. GitHub Pages는 씌워주지 않으므로 `build_pages.py`가
  charset·viewport와 함께 감싸서 `docs/`에 냅니다. 조각을 그대로 올리면 한글이 깨집니다.
- 받아온 SVG의 절반쯤은 `viewBox` 없이 `width`/`height`만 갖고 있습니다. 그 둘을 지우면
  비율 기준이 사라져 국기가 확대되어 잘립니다. `make_js.py`가 지우기 전에 `viewBox`를
  만들어 넣습니다.

## 출처

국기 이미지는 [flagcdn.com](https://flagcdn.com) (퍼블릭 도메인).
글꼴은 Google Fonts의 Jua, Fredoka.
