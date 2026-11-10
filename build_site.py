"""
정부대전청사 구내식당 식단표 페이지 생성기

정부청사관리본부(gbmo.go.kr)에서 대전청사 식당별 최신 식단 이미지를 받아
docs/ 폴더에 정적 웹페이지(index.html + 이미지)를 만든다.
GitHub Actions가 매일 실행하고, GitHub Pages가 docs/ 폴더를 공개한다.

로컬 실행:  python build_site.py   → docs/index.html 을 브라우저로 열기
"""

import hashlib
import html
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

GBMO = "https://www.gbmo.go.kr"
DIET_API = f"{GBMO}/chungsa/dv/dietView"
DAEJEON = "CD003"  # 대전청사 코드
SOURCE_PAGE = f"{DIET_API}/selectDietCalendarView.do?mi=1277&gbd={DAEJEON}"
HEADERS = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json; charset=UTF-8"}
KST = ZoneInfo("Asia/Seoul")
WEEKDAYS = "월화수목금토일"

OUT = Path(__file__).resolve().parent / "docs"
IMG_DIR = OUT / "img"


def post(path, **params):
    r = requests.post(f"{DIET_API}/{path}", json={"sysId": "chungsa", "gbd": DAEJEON, **params},
                      headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_menus():
    """대전청사 식당별 최신 식단 정보 + 이미지 바이트."""
    menus = []
    for r in post("selectRstrntList.do"):
        code, name = r["rstrntCode"], r["rstrntName"]
        result = post("selectDietView.do", rc=code)
        if not result:
            menus.append({"code": code, "name": name})
            continue
        d = result[0]
        img = requests.get(GBMO + d["fileStreCours"], headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        img.raise_for_status()
        menus.append({
            "code": code,
            "name": name,
            "ext": (d.get("fileExtsn") or "jpg").lower(),
            "bytes": img.content,
            "week": datetime.fromtimestamp(d["dietDate"] / 1000, KST),
        })
    return menus


def write_images(menus):
    """이미지를 docs/img/<식당코드>.<확장자> 로 저장 (이전 파일은 정리)."""
    if IMG_DIR.exists():
        shutil.rmtree(IMG_DIR)
    IMG_DIR.mkdir(parents=True)
    for m in menus:
        if "bytes" not in m:
            continue
        fname = f"{m['code']}.{m['ext']}"
        (IMG_DIR / fname).write_bytes(m["bytes"])
        # 이미지가 바뀌면 주소도 바뀌게 해서 휴대폰 캐시에 옛 식단이 남지 않도록
        m["src"] = f"img/{fname}?v={hashlib.md5(m['bytes']).hexdigest()[:8]}"


def render(menus):
    now = datetime.now(KST)
    chips, cards = [], []
    for m in menus:
        name = html.escape(m["name"])
        anchor = f"r{m['code']}"
        chips.append(f'<a class="chip" href="#{anchor}">{name}</a>')
        if "src" in m:
            body = (f'<a href="{m["src"]}" target="_blank" rel="noopener" class="img-link">'
                    f'<img src="{m["src"]}" alt="{name} 주간 식단표" loading="lazy"></a>'
                    f'<a class="open" href="{m["src"]}" target="_blank" rel="noopener">원본 크게 보기 ↗</a>')
            week = f'{m["week"]:%m/%d}({WEEKDAYS[m["week"].weekday()]}) 주'
        else:
            body = '<p class="empty">등록된 식단이 없습니다.</p>'
            week = ""
        cards.append(f'''
    <section class="card" id="{anchor}">
      <div class="card-head"><h2>{name}</h2><span class="week">{week}</span></div>
      {body}
    </section>''')

    return f'''<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>대전청사 식단표</title>
<meta name="description" content="정부대전청사 구내식당 주간 식단표 모음 (매일 자동 갱신)">
<meta property="og:title" content="정부대전청사 구내식당 식단표">
<meta property="og:description" content="1·2동, 3·4동, 양식당, 후생동 식단을 한 화면에서">
<style>
  :root {{
    --bg: #f4f6fb; --card: #fff; --text: #1d2433; --muted: #667085;
    --accent: #21409a; --chip: #e7ecf8; --line: #e3e7ef;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg: #12151c; --card: #1b2029; --text: #e8ebf2; --muted: #9aa3b5;
             --accent: #8fa8ff; --chip: #262d3b; --line: #2b3240; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--text);
         font-family: -apple-system, "Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans KR", sans-serif; }}
  header {{ background: var(--accent); color: #fff; padding: 20px 16px 16px; }}
  @media (prefers-color-scheme: dark) {{ header {{ background: #1f2f66; }} }}
  header h1 {{ margin: 0 0 4px; font-size: 1.35rem; }}
  header p {{ margin: 0; font-size: .85rem; opacity: .85; }}
  nav {{ position: sticky; top: 0; z-index: 1; display: flex; gap: 8px; overflow-x: auto;
        padding: 10px 16px; background: var(--bg); border-bottom: 1px solid var(--line); }}
  .chip {{ flex: none; padding: 7px 14px; border-radius: 999px; background: var(--chip);
          color: var(--accent); text-decoration: none; font-size: .9rem; font-weight: 600; }}
  main {{ max-width: 1100px; margin: 0 auto; padding: 12px 16px 32px; }}
  .card {{ background: var(--card); border-radius: 14px; padding: 14px; margin: 14px 0;
          box-shadow: 0 1px 3px rgba(0,0,0,.06); scroll-margin-top: 64px; }}
  .card-head {{ display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin-bottom: 10px; }}
  .card-head h2 {{ margin: 0; font-size: 1.15rem; }}
  .week {{ color: var(--muted); font-size: .85rem; }}
  .img-link img {{ display: block; width: 100%; height: auto; border-radius: 8px; background: #fff; }}
  .open {{ display: inline-block; margin-top: 10px; color: var(--accent); font-size: .9rem; font-weight: 600; text-decoration: none; }}
  .empty {{ color: var(--muted); }}
  footer {{ text-align: center; color: var(--muted); font-size: .8rem; padding: 0 16px 28px; }}
  footer a {{ color: var(--muted); }}
</style>
</head>
<body>
<header>
  <h1>🍱 정부대전청사 구내식당 식단표</h1>
  <p>마지막 확인 {now:%Y.%m.%d}({WEEKDAYS[now.weekday()]}) {now:%H:%M} · 평일 아침 자동 갱신</p>
</header>
<nav>{"".join(chips)}</nav>
<main>{"".join(cards)}
</main>
<footer>이미지를 누르면 원본 크기로 열립니다 (확대 가능)<br>
출처: <a href="{SOURCE_PAGE}" target="_blank" rel="noopener">행정안전부 정부청사관리본부</a></footer>
</body>
</html>
'''


def main():
    menus = fetch_menus()
    OUT.mkdir(exist_ok=True)
    write_images(menus)
    (OUT / "index.html").write_text(render(menus), encoding="utf-8")
    (OUT / ".nojekyll").touch()  # GitHub Pages가 파일을 그대로 공개하도록
    for m in menus:
        print(f"{m['name']}: {'OK ' + m['src'] if 'src' in m else '식단 없음'}")


if __name__ == "__main__":
    main()
