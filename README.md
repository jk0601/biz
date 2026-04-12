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

## 정적 HTML

`docs/bizinfolist.html`은 실행 시마다 덮어씁니다. GitHub Pages 등으로 올릴 때는 이 파일(및 필요 시 `docs/img/favicon.ico`)을 함께 배포하면 됩니다.
