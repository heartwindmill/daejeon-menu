# 정부대전청사 구내식당 식단표

👉 **https://heartwindmill.github.io/daejeon-menu/**

정부대전청사 구내식당 4곳(1·2동, 3·4동, 양식당, 후생동 식당)의 주간 식단표를 한 화면에 모아 보여줍니다.
평일 오전 9시쯤 GitHub Actions가 [정부청사관리본부](https://www.gbmo.go.kr/chungsa/dv/dietView/selectDietCalendarView.do?mi=1277&gbd=CD003)에서 최신 식단을 받아 자동으로 갱신합니다. 실패하면 페이지에 "갱신 실패"가 표시되고 10시에 한 번 더 시도합니다.

- `build_site.py`: 식단 이미지를 받아 `docs/`에 페이지 생성
- `.github/workflows/update-menu.yml`: 매일 실행 + 변경 사항 커밋
- 지금 바로 갱신: Actions 탭 → "식단표 갱신" → Run workflow
