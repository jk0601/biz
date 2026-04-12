import html
import os
import re
import requests
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
from notion_client import Client

load_dotenv()

BIZINFO_API_KEY = os.getenv("BIZINFO_API_KEY")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DB_ID = os.getenv("NOTION_DB_ID")

BASE_URL = "https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do"

notion = Client(auth=NOTION_TOKEN)


def fetch_today_announcements(collect_days=2):
    """서울·경기 지역의 최근 N일 등록 공고 수집
    - collect_days=1: 어제·오늘 (2일치, 기본값)
    - collect_days=2: 그저께·어제·오늘 (3일치), 6은 일주일치 데이터 수집
    - API는 areaCd와 무관하게 전국 데이터 반환 → jrsdInsttNm으로 서울/경기만 필터
    """
    valid_dates = tuple(
        (date.today() - timedelta(days=i)).strftime("%Y%m%d")
        for i in range(collect_days + 1)
    )
    seen_ids = set()
    results = []

    for area_cd, _ in [("11", "서울"), ("41", "경기")]:
        params = {
            "crtfcKey": BIZINFO_API_KEY,
            "dataType": "json",
            "areaCd": area_cd,
            "pageIndex": 1,
            "pageUnit": 100,
        }
        try:
            res = requests.get(BASE_URL, params=params, timeout=10)
            res.raise_for_status()
            data = res.json()

            # 응답 구조 확인용 (처음 실행 시 주석 해제해서 확인)
            # import json; print(json.dumps(data, ensure_ascii=False, indent=2))

            items = data.get("jsonArray", data.get("items", []))
            if isinstance(items, dict):
                items = [items]

            for item in items:
                # creatPnttm(등록일) 기준: valid_dates 범위 내만
                reg_date = item.get("creatPnttm", "").replace("-", "").replace(" ", "")[:8]
                if reg_date not in valid_dates:
                    continue

                # 서울·경기만: jrsdInsttNm(공고기관)으로 지역 판별 (경상남도 등 제외)
                agency = item.get("jrsdInsttNm") or ""
                if "서울" in agency:
                    area_name = "서울"
                elif "경기도" in agency:
                    area_name = "경기"
                else:
                    continue

                pblanc_id = item.get("pblancId") or ""
                if pblanc_id and pblanc_id in seen_ids:
                    continue
                seen_ids.add(pblanc_id)
                item["area_name"] = area_name
                results.append(item)

        except Exception as e:
            print(f"[ERROR] API 호출 실패: {e}")

    return results


def is_duplicate(pblanc_id):
    """이미 Notion에 등록된 공고인지 확인"""
    try:
        res = notion.databases.query(
            database_id=NOTION_DB_ID,
            filter={
                "property": "공고ID",
                "rich_text": {"equals": pblanc_id}
            }
        )
        return len(res["results"]) > 0
    except Exception as e:
        print(f"[ERROR] 중복 확인 실패: {e}")
        return False


def create_notion_page(item):
    """Notion 데이터베이스에 공고 페이지 생성"""
    today = date.today().strftime("%Y%m%d")

    pblanc_id  = item.get("pblancId") or ""
    title_text = item.get("pblancNm") or "제목없음"
    agency     = item.get("jrsdInsttNm") or ""
    category   = item.get("pldirSportRealmLclasCodeNm") or ""

    # 등록일: creatPnttm "2026-02-26 15:21:29" → "2026-02-26"
    creat_pnttm = item.get("creatPnttm") or ""
    reg_date_iso = creat_pnttm[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", creat_pnttm) else ""

    # 접수마감: "2026-02-13 ~ 2026-03-19" → 종료일만, "예산 소진시까지"/"상시 접수"/"선착순 접수" 등 → 문자 그대로
    req_period = item.get("reqstBeginEndDe") or ""
    req_period = req_period.strip()
    if "~" in req_period:
        end_part = req_period.split("~")[-1].strip()
        # YYYY-MM-DD 형식이면 종료일만, 아니면 전체 문자열 사용
        deadline_value = end_part if re.match(r"^\d{4}-\d{2}-\d{2}$", end_part) else req_period
    else:
        deadline_value = req_period
    # 빈 문자열이면 저장하지 않음
    if not deadline_value:
        deadline_value = ""

    # 공고 URL: 상대경로에 도메인 붙이기
    pblanc_url = item.get("pblancUrl") or ""
    if pblanc_url.startswith("/"):
        pblanc_url = "https://www.bizinfo.go.kr" + pblanc_url

    page_title = f"{today}_{title_text}"

    properties = {
        "제목":    {"title": [{"text": {"content": page_title}}]},
        "지역":    {"select": {"name": item["area_name"]}},
        "공고기관": {"rich_text": [{"text": {"content": agency}}]},
        "공고ID":  {"rich_text": [{"text": {"content": pblanc_id}}]},
    }

    if reg_date_iso:
        properties["등록일"] = {"date": {"start": reg_date_iso}}

    # 접수마감: 날짜·문자 모두 저장 (Notion 속성은 텍스트로 설정)
    if deadline_value:
        properties["접수마감일"] = {"rich_text": [{"text": {"content": deadline_value}}]}

    if pblanc_url:
        properties["공고URL"] = {"url": pblanc_url}

    if category:
        # Notion DB에서 지원분야가 multi_select 타입인 경우
        properties["지원분야"] = {"multi_select": [{"name": category}]}

    notion.pages.create(
        parent={"database_id": NOTION_DB_ID},
        properties=properties,
    )
    return page_title


def _prop_plain_text(prop):
    """Notion rich_text / title → 단일 문자열."""
    if not prop:
        return ""
    ptype = prop.get("type")
    if ptype == "title":
        parts = prop.get("title") or []
    elif ptype == "rich_text":
        parts = prop.get("rich_text") or []
    else:
        return ""
    return "".join((p.get("plain_text") or p.get("text", {}).get("content") or "") for p in parts)


def _prop_select_name(prop):
    if not prop or prop.get("type") != "select":
        return ""
    sel = prop.get("select")
    return (sel or {}).get("name") or ""


def _prop_date_start(prop):
    if not prop or prop.get("type") != "date":
        return ""
    d = prop.get("date")
    if not d:
        return ""
    return d.get("start") or ""


def _prop_url(prop):
    if not prop or prop.get("type") != "url":
        return ""
    return prop.get("url") or ""


def _prop_multi_select_names(prop):
    if not prop or prop.get("type") != "multi_select":
        return ""
    items = prop.get("multi_select") or []
    return ", ".join((x.get("name") or "") for x in items if x.get("name"))


def shorten_export_title(full_title: str, region_name: str) -> str:
    """제목에서 YYYYMMDD_ 접두와 [지역명] 접두를 제거한 뒤 15자 + 필요 시 '...'."""
    s = (full_title or "").strip()
    m = re.match(r"^\d{8}_(.*)$", s, flags=re.DOTALL)
    if m:
        s = m.group(1).strip()
    if region_name:
        bracket = f"[{region_name}]"
        if s.startswith(bracket):
            s = s[len(bracket) :].lstrip()
    if len(s) > 15:
        return s[:15] + "..."
    return s


def query_all_notion_db_pages():
    """데이터베이스 전체 페이지(페이지네이션)."""
    all_rows = []
    start_cursor = None
    while True:
        kwargs = {
            "database_id": NOTION_DB_ID,
            "page_size": 100,
            "sorts": [{"property": "등록일", "direction": "descending"}],
        }
        if start_cursor:
            kwargs["start_cursor"] = start_cursor
        res = notion.databases.query(**kwargs)
        all_rows.extend(res.get("results") or [])
        if not res.get("has_more"):
            break
        start_cursor = res.get("next_cursor")
    return all_rows


def build_export_rows_from_notion():
    """Notion 행 → (등록일, 지역, 짧은제목, 지원분야, 공고URL, 접수마감일) 목록."""
    rows_out = []
    for page in query_all_notion_db_pages():
        props = page.get("properties") or {}
        full_title = _prop_plain_text(props.get("제목"))
        region = _prop_select_name(props.get("지역"))
        reg = _prop_date_start(props.get("등록일"))
        category = _prop_multi_select_names(props.get("지원분야"))
        url = _prop_url(props.get("공고URL"))
        deadline = _prop_plain_text(props.get("접수마감일"))
        short_title = shorten_export_title(full_title, region)
        rows_out.append(
            {
                "등록일": reg,
                "지역": region,
                "제목": short_title,
                "지원분야": category,
                "공고URL": url,
                "접수마감일": deadline,
            }
        )
    return rows_out


def write_bizinfolist_html(rows, output_path: Path):
    """docs/bizinfolist.html — 작은 글자, 테이블 레이아웃."""
    thead = (
        "<tr>"
        "<th>등록일</th><th>지역</th><th>제목</th>"
        "<th>지원분야</th><th>공고URL</th><th>접수마감일</th>"
        "</tr>"
    )
    body_rows = []
    for r in rows:
        url = r["공고URL"]
        url_cell = (
            f'<a href="{html.escape(url, quote=True)}">링크</a>'
            if url
            else ""
        )
        body_rows.append(
            "<tr>"
            f"<td>{html.escape(r['등록일'])}</td>"
            f"<td>{html.escape(r['지역'])}</td>"
            f"<td class=\"col-title\">{html.escape(r['제목'])}</td>"
            f"<td>{html.escape(r['지원분야'])}</td>"
            f"<td class=\"col-url\">{url_cell}</td>"
            f"<td>{html.escape(r['접수마감일'])}</td>"
            "</tr>"
        )

    doc = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>지원사업 공고 목록</title>
  <style>
    :root {{
      --text: #1a1a1a;
      --muted: #5c5c5c;
      --border: #d8d8d8;
      --row-alt: #fafbfc;
      --white: #ffffff;
      --navy: #1a2d4a;
      --navy-mid: #2a3f5c;
      --silver-light: #c8d0da;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      padding: 1.25rem 0.85rem 2rem;
      font-family: "Malgun Gothic", "Apple SD Gothic Neo", "Segoe UI", sans-serif;
      font-size: 0.8125rem;
      line-height: 1.55;
      color: var(--text);
      background: linear-gradient(165deg, #dfe4ea 0%, #edf1f5 42%, #f1f3f8 100%);
    }}
    .sheet {{
      max-width: 1100px;
      margin: 0 auto;
      padding: 1rem 1.1rem 1.25rem;
      background: #ffffff;
      border-radius: 12px;
      box-shadow: 0 4px 24px rgba(15, 23, 42, 0.08), 0 1px 3px rgba(15, 23, 42, 0.06);
    }}
    h1 {{
      font-size: 14px;
      font-weight: 600;
      margin: 0 0 10px;
      color: var(--muted);
    }}
    .meta {{
      font-size: 11px;
      color: var(--muted);
      margin-bottom: 12px;
    }}
    table {{
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      font-size: 11px;
      table-layout: fixed;
    }}
    th, td {{
      vertical-align: top;
      word-break: break-word;
    }}
    td {{
      border: 1px solid var(--border);
      padding: 6px 8px;
    }}
    th {{
      background: linear-gradient(180deg, var(--navy) 0%, var(--navy-mid) 100%);
      color: var(--white);
      font-weight: 600;
      font-size: 0.7rem;
      letter-spacing: 0.02em;
      padding: 0.38rem 0.55rem;
      text-align: left;
      white-space: nowrap;
      border-top: 1px solid rgba(255, 255, 255, 0.12);
      border-right: 1px solid rgba(255, 255, 255, 0.12);
      border-bottom: 1px solid var(--silver-light);
      border-left: none;
    }}
    th:first-child {{
      border-left: 1px solid rgba(255, 255, 255, 0.12);
      border-top-left-radius: 10px;
    }}
    th:last-child {{
      border-top-right-radius: 10px;
    }}
    tbody tr:first-child td {{
      border-top: none;
    }}

    tr:nth-child(even) td {{ background: var(--row-alt); }}
    th:nth-child(1), td:nth-child(1) {{ width: 88px; }}
    th:nth-child(2), td:nth-child(2) {{ width: 48px; }}
    th:nth-child(3), td:nth-child(3) {{ width: 22%; }}
    th:nth-child(4), td:nth-child(4) {{ width: 18%; }}
    th:nth-child(5), td:nth-child(5) {{ width: 52px; text-align: center; }}
    th:nth-child(6), td:nth-child(6) {{ width: 96px; }}
    .col-title {{ font-size: 11px; }}
    .col-url a {{
      color: #1565c0;
      text-decoration: none;
      font-size: 11px;
    }}
    .col-url a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <div class="sheet">
    <h1><img src="img/favicon.ico" alt="favicon" style="width: 20px; height: 20px; vertical-align: middle;"> 지원사업 공고 목록</h1>
    <hr>
    <p class="meta">갱신: {html.escape(date.today().isoformat())} · 총 {len(rows)}건</p>
    <table>
      <thead>{thead}</thead>
      <tbody>
        {''.join(body_rows) if body_rows else '<tr><td colspan="6">데이터가 없습니다.</td></tr>'}
      </tbody>
    </table>
  </div>
</body>
</html>
"""
    output_path.write_text(doc, encoding="utf-8")


def export_bizinfolist_html():
    """docs 폴더에 Notion DB 기준 bizinfolist.html 저장."""
    docs_dir = Path(__file__).resolve().parent / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    rows = build_export_rows_from_notion()
    out = docs_dir / "bizinfolist.html"
    write_bizinfolist_html(rows, out)
    return out, len(rows)


def main():
    print(f"[{date.today()}] 지원사업 공고 수집 시작")

    announcements = fetch_today_announcements()
    print(f"당일 공고 총 {len(announcements)}건 발견")

    created, skipped = 0, 0
    for item in announcements:
        pblanc_id = item.get("pblancId") or ""

        if pblanc_id and is_duplicate(pblanc_id):
            print(f"  [SKIP] 중복: {item.get('pblancNm')}")
            skipped += 1
            continue

        try:
            page_title = create_notion_page(item)
            print(f"  [OK] {page_title}")
            created += 1
        except Exception as e:
            print(f"  [ERROR] Notion 페이지 생성 실패: {e}")

    print(f"\n완료 - 생성: {created}건 / 중복 건너뜀: {skipped}건")

    try:
        path, n = export_bizinfolist_html()
        print(f"HTML보내기: {path} ({n}건)")
    except Exception as e:
        print(f"[WARN] bizinfolist.html 저장 실패: {e}")


if __name__ == "__main__":
    main()