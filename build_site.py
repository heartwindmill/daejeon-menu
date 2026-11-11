"""
정부대전청사 구내식당 식단표 페이지 생성기

정부청사관리본부(gbmo.go.kr)에서 대전청사 식당별 최신 식단 이미지를 받아
docs/ 폴더에 정적 웹페이지(index.html + 이미지)를 만든다.
GitHub Actions가 매일 실행하고, GitHub Pages가 docs/ 폴더를 공개한다.

로컬 실행:  python build_site.py   → docs/index.html 을 브라우저로 열기
"""

import hashlib
import html
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

GBMO = "https://www.gbmo.go.kr"
DIET_API = f"{GBMO}/chungsa/dv/dietView"
DAEJEON = "CD003"  # 대전청사 코드
SOURCE_PAGE = f"{DIET_API}/selectDietCalendarView.do?mi=1277&gbd={DAEJEON}"
KST = ZoneInfo("Asia/Seoul")
WEEKDAYS = "월화수목금토일"

OUT = Path(__file__).resolve().parent / "docs"
IMG_DIR = OUT / "img"
STATUS_FILE = OUT / "status.json"  # 오늘 갱신 성공 여부 (10시 재실행이 확인용으로 읽음)


# 식당 목록 조회가 막혔을 때 쓰는 기본 목록
DEFAULT_RESTAURANTS = [("1049", "1동, 2동"), ("1050", "3동, 4동"), ("1051", "양식당"), ("1052", "후생동 식당")]

# 정부 사이트 보안장비가 연속 요청을 끊는 경우가 있어 브라우저처럼 보이게 하고 간격을 둔다
session = requests.Session()
session.headers.update({
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": SOURCE_PAGE,
})


def with_retry(func, what, tries=4):
    for i in range(1, tries + 1):
        try:
            time.sleep(1.5)
            return func()
        except requests.RequestException as e:
            print(f"  [{what}] {i}/{tries}회 실패: {e}")
            if i == tries:
                raise
            time.sleep(5 * i)


def post(path, **params):
    def call():
        r = session.post(f"{DIET_API}/{path}", json={"sysId": "chungsa", "gbd": DAEJEON, **params},
                         headers={"Content-Type": "application/json; charset=UTF-8",
                                  "Accept": "application/json, text/javascript, */*; q=0.01",
                                  "X-Requested-With": "XMLHttpRequest", "Origin": GBMO},
                         timeout=30)
        r.raise_for_status()
        return r.json()
    return with_retry(call, path)


def find_image_from_page(code):
    """대체 경로: 일반 식단 페이지(HTML)에서 이미지 주소를 찾는다."""
    def call():
        r = session.get(f"{SOURCE_PAGE}&rc={code}", timeout=30)
        r.raise_for_status()
        return r.text
    m = re.search(r'<img src="(/NAS/jboss/uploads/chungsa/di/[^"]+)" data-id="diet"', with_retry(call, f"page {code}"))
    return m.group(1) if m else None


def get_restaurants():
    try:
        return [(r["rstrntCode"], r["rstrntName"]) for r in post("selectRstrntList.do")]
    except requests.RequestException:
        print("식당 목록 조회 실패 → 기본 목록 사용")
        return DEFAULT_RESTAURANTS


def fetch_menu(code, name):
    """식당 1곳의 최신 식단 이미지. 조회 API → 실패 시 일반 페이지 순서로 시도."""
    path, ext, week = None, None, None
    try:
        result = post("selectDietView.do", rc=code)
        if not result:
            return {"code": code, "name": name, "status": "empty"}
        d = result[0]
        path, ext = d.get("fileStreCours"), (d.get("fileExtsn") or "").lower()
        if d.get("dietDate"):
            week = datetime.fromtimestamp(d["dietDate"] / 1000, KST)
    except (requests.RequestException, ValueError, KeyError, TypeError, IndexError):
        print(f"  {name}: 조회 API 실패 → 일반 페이지에서 찾기")
        path = find_image_from_page(code)
        if not path:
            return {"code": code, "name": name, "status": "empty"}
    if not path:  # 조회는 됐는데 이미지 주소가 아직 없음 = 식단이 덜 올라옴
        raise ValueError("식단 이미지 주소가 비어 있음")

    ext = ext or path.rsplit(".", 1)[-1].lower()
    img = with_retry(lambda: session.get(GBMO + path, timeout=60), f"image {code}")
    img.raise_for_status()
    return {"code": code, "name": name, "ext": ext, "bytes": img.content, "week": week, "status": "ok"}


def fetch_menus():
    menus = []
    for code, name in get_restaurants():
        try:
            menus.append(fetch_menu(code, name))
        except Exception as e:  # 어떤 오류든 이 식당만 실패 처리하고 나머지는 계속
            print(f"  {name}: 가져오기 실패 ({e}) → 이전 식단 유지")
            menus.append({"code": code, "name": name, "status": "failed"})
    return menus


def write_images(menus):
    """이미지를 docs/img/<식당코드>.<확장자> 로 저장. 이번에 못 받은 식당은 이전 파일 유지."""
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    keep = set()
    for m in menus:
        if m["status"] == "ok":
            fname = f"{m['code']}.{m['ext']}"
            (IMG_DIR / fname).write_bytes(m["bytes"])
        elif m["status"] == "failed":
            old = sorted(IMG_DIR.glob(f"{m['code']}.*"))
            if not old:
                continue
            fname = old[0].name
            m["bytes"] = old[0].read_bytes()
        else:
            continue
        keep.add(fname)
        # 이미지가 바뀌면 주소도 바뀌게 해서 휴대폰 캐시에 옛 식단이 남지 않도록
        m["src"] = f"img/{fname}?v={hashlib.md5(m['bytes']).hexdigest()[:8]}"
    for f in IMG_DIR.iterdir():
        if f.name not in keep:
            f.unlink()


def render(menus, retry_later):
    now = datetime.now(KST)
    failed = sum(m["status"] == "failed" for m in menus)
    banner = ""
    if failed:
        what = "갱신 실패" if failed == len(menus) else f"{failed}곳 갱신 실패"
        plan = "10시에 다시 시도합니다" if retry_later else "이전 식단을 표시 중입니다"
        banner = f'<p class="fail">⚠ {now:%H:%M} {what} · {plan}</p>'
    chips, cards = [], []
    for m in menus:
        name = html.escape(m["name"])
        anchor = f"r{m['code']}"
        chips.append(f'<a class="chip" href="#{anchor}">{name}</a>')
        if "src" in m:
            body = (f'<a href="{m["src"]}" target="_blank" rel="noopener" class="img-link">'
                    f'<img src="{m["src"]}" alt="{name} 주간 식단표" loading="lazy"></a>'
                    f'<a class="open" href="{m["src"]}" target="_blank" rel="noopener">원본 크게 보기 ↗</a>')
            week = f'{m["week"]:%m/%d}({WEEKDAYS[m["week"].weekday()]}) 주' if m.get("week") else ""
            if m["status"] == "failed":
                week = "⚠ 오늘 갱신 실패 · 이전 식단"
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
  header p.fail {{ display: inline-block; margin-top: 8px; padding: 5px 10px; border-radius: 8px;
                  background: #ffe2e0; color: #b42318; opacity: 1; font-weight: 700; }}
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
  <p>마지막 확인 {now:%Y.%m.%d}({WEEKDAYS[now.weekday()]}) {now:%H:%M} · 평일 9시 자동 갱신</p>
  {banner}
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
    # RETRY_LATER=1 이면 실패 시 "10시에 다시 시도" 문구 표시 (워크플로의 9시 실행이 설정)
    retry_later = os.environ.get("RETRY_LATER") == "1"
    menus = fetch_menus()
    OUT.mkdir(exist_ok=True)
    write_images(menus)  # 실패한 식당은 이전 이미지 유지
    (OUT / "index.html").write_text(render(menus, retry_later), encoding="utf-8")
    (OUT / ".nojekyll").touch()  # GitHub Pages가 파일을 그대로 공개하도록
    ok = not any(m["status"] == "failed" for m in menus)
    now = datetime.now(KST)
    STATUS_FILE.write_text(json.dumps({"date": f"{now:%Y-%m-%d}", "time": f"{now:%H:%M}", "ok": ok},
                                      ensure_ascii=False), encoding="utf-8")
    for m in menus:
        print(f"{m['name']}: {'OK ' + m['src'] if 'src' in m else ('실패' if m['status'] == 'failed' else '식단 없음')}")
    if not ok:
        # 페이지에는 실패 표시를 남기고, Actions에는 빨간 X로 알린다
        sys.exit("일부 또는 전체 식당 식단을 가져오지 못했습니다.")


if __name__ == "__main__":
    main()
