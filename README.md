# biz — 기업마당 공고 → Notion

서울·경기 지역 최근 등록 공고를 [기업마당 Open API](https://www.bizinfo.go.kr)로 가져와 Notion 데이터베이스에 추가하고, 같은 DB를 읽어 `docs/bizinfolist.html` 목록을 갱신합니다.

## 필요 환경

- Python 3.11 권장 (GitHub Actions와 동일)
- `.env` 파일 (`.env.example` 참고)

## 로컬 실행

```bash
python -m venv venv
# Windows: venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # 또는 수동으로 .env 생성 후 값 입력
python main.py
```

## GitHub Actions

`.github/workflows/daily.yml`이 매일 UTC 0시(한국 09:00)에 `main.py`를 실행합니다. 저장소 **Settings → Secrets and variables → Actions**에 다음 시크릿을 등록하세요.

| 이름 | 설명 |
|------|------|
| `BIZINFO_API_KEY` | 기업마당 API 인증키 |
| `NOTION_TOKEN` | Notion 통합 토큰 |
| `NOTION_DB_ID` | 대상 데이터베이스 ID |

워크플로는 `python main.py`로 `docs/bizinfolist.html`을 만든 뒤, 내용이 바뀌었을 때만 해당 파일을 **커밋해 같은 브랜치에 푸시**합니다. 그래서 저장소에 있는 HTML이 스케줄·수동 실행마다 최신으로 맞춰집니다. (`main` 등에 브랜치 보호로 푸시가 막혀 있으면 이 단계는 실패할 수 있습니다.)

## 정적 HTML

`docs/bizinfolist.html`은 실행 시마다 덮어씁니다. GitHub Pages는 보통 `main`의 `docs/`를 소스로 두면, 위 푸시와 맞물려 목록이 갱신됩니다.
