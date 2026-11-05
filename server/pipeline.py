"""
넷플릭스 TOP10 + AI 해설 데이터 파이프라인
================================================
흐름
  1) Netflix Tudum 공식 주간 TOP10 (기준 데이터)  ── 한국(KR) + 글로벌
  2) FlixPatrol 일간 순위 (보조 트렌드, 유료 API 키가 있을 때만)
  3) TMDB 에서 한국어 제목·공식 줄거리·장르·포스터 보강 (AI 사실 근거)
  4) Claude 가 한국어 줄거리 / 스포일러 없는 감상 포인트 / 추천 이유 생성
     - 작품별로 한 번만 생성하고 cache/ai_cache.json 에 저장 (비용 절감)
  5) 결과를 output/top10.json 으로 저장 → 앱이 이 파일 하나만 읽는다

실행
  pip install -r requirements.txt
  python pipeline.py            # 전체 실행
  python pipeline.py --no-ai    # AI 생성 없이 데이터만 (테스트용)

필요한 키 (환경변수 또는 .env 파일)
  ANTHROPIC_API_KEY   : Claude API 키 (AI 해설)
  TMDB_API_KEY        : TMDB v3 API 키 (한국어 제목·줄거리·포스터)
  FLIXPATROL_API_KEY  : (선택) FlixPatrol 유료 API 키
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

BASE = Path(__file__).resolve().parent
OUT_DIR = BASE / "output"
CACHE_DIR = BASE / "cache"
OUT_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)

TUDUM_GLOBAL = "https://www.netflix.com/tudum/top10/data/all-weeks-global.tsv"
TUDUM_COUNTRIES = "https://www.netflix.com/tudum/top10/data/all-weeks-countries.tsv"
COUNTRY = os.getenv("TOP10_COUNTRY", "KR")
UA = {"User-Agent": "Mozilla/5.0 (Top10KR data pipeline)"}

TMDB_KEY = os.getenv("TMDB_API_KEY", "").strip()
TMDB_IMG = "https://image.tmdb.org/t/p/w500"
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")

AI_CACHE_FILE = CACHE_DIR / "ai_cache.json"
TMDB_CACHE_FILE = CACHE_DIR / "tmdb_cache_v2.json"   # v2: 작품 매칭 방식 개선
OLD_TMDB_CACHE_FILE = CACHE_DIR / "tmdb_cache.json"  # v1: 기존 해설이 어떤 작품 기준이었는지 확인용


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def title_key(show_title: str, season_title: str | None) -> str:
    s = (season_title or "").strip()
    return f"{show_title.strip()}||{s if s and s != 'N/A' else ''}"


# ---------------------------------------------------------------------------
# 1) Netflix Tudum 공식 주간 TOP10 (기준 데이터)
# ---------------------------------------------------------------------------
def _stream_tsv(url: str):
    r = requests.get(url, headers=UA, timeout=120, stream=True)
    r.raise_for_status()
    r.encoding = "utf-8"
    lines = (ln for ln in r.iter_lines(decode_unicode=True) if ln)
    yield from csv.DictReader(lines, delimiter="\t")


def fetch_tudum_global() -> tuple[str, list[dict]]:
    """글로벌 TOP10 중 가장 최근 주(week)만 반환. 시청수·시청시간 포함."""
    rows = list(_stream_tsv(TUDUM_GLOBAL))
    latest = max(r["week"] for r in rows)
    items = []
    for r in rows:
        if r["week"] != latest:
            continue
        items.append(
            {
                "rank": int(r["weekly_rank"]),
                "category": r["category"],  # Films (English) / TV (Non-English) 등
                "type": "tv" if r["category"].startswith("TV") else "movie",
                "show_title": r["show_title"],
                "season_title": None if r["season_title"] in ("", "N/A") else r["season_title"],
                "weekly_views": _to_int(r.get("weekly_views")),
                "weekly_hours_viewed": _to_int(r.get("weekly_hours_viewed")),
                "weeks_in_top10": _to_int(r.get("cumulative_weeks_in_top_10")),
            }
        )
    items.sort(key=lambda x: (x["category"], x["rank"]))
    return latest, items


def fetch_tudum_country(iso2: str) -> tuple[str, list[dict]]:
    """국가별 TOP10(기본 한국) 최근 주. 파일이 30MB+ 이므로 스트리밍으로 해당 국가만 추린다."""
    rows = [r for r in _stream_tsv(TUDUM_COUNTRIES) if r["country_iso2"] == iso2]
    weeks = sorted({r["week"] for r in rows})
    latest = weeks[-1]
    prev = weeks[-2] if len(weeks) > 1 else None
    # 지난주 순위 (같은 구분 안에서 비교: 영화끼리 / 시리즈끼리)
    prev_rank = {
        (r["category"], title_key(r["show_title"], r["season_title"])): int(r["weekly_rank"])
        for r in rows if r["week"] == prev
    }
    items = []
    for r in rows:
        if r["week"] != latest:
            continue
        rank = int(r["weekly_rank"])
        before = prev_rank.get((r["category"], title_key(r["show_title"], r["season_title"])))
        weeks = _to_int(r.get("cumulative_weeks_in_top_10")) or 1
        items.append(
            {
                "rank": rank,
                "category": r["category"],  # Films / TV
                "type": "tv" if r["category"].startswith("TV") else "movie",
                "show_title": r["show_title"],
                "season_title": None if r["season_title"] in ("", "N/A") else r["season_title"],
                "weeks_in_top10": _to_int(r.get("cumulative_weeks_in_top_10")),
                "is_new": before is None and weeks <= 1,        # 이번 주 처음 진입
                "re_entry": before is None and weeks > 1,       # 지난주엔 없었지만 예전에 있던 작품
                "rank_change": None if before is None else before - rank,  # +면 상승
            }
        )
    items.sort(key=lambda x: (x["category"], x["rank"]))
    return latest, items


def _to_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 2) FlixPatrol 일간 트렌드 (보조 자료)
#    - FlixPatrol 은 유료 API(Start $9.99/월~)를 제공한다. 웹페이지 무단 수집(스크래핑)은
#      약관 위반 위험이 있으므로 이 코드는 "API 키가 있을 때만" 동작한다.
#    - 엔드포인트·필드명은 계약 후 받는 API 문서에 맞춰 FLIXPATROL_ENDPOINT 와
#      _map_flixpatrol_row() 두 곳만 수정하면 된다.
# ---------------------------------------------------------------------------
def fetch_flixpatrol_daily() -> dict | None:
    key = os.getenv("FLIXPATROL_API_KEY")
    endpoint = os.getenv("FLIXPATROL_ENDPOINT")  # 예: API 문서의 'Netflix 한국 일간 TOP10' URL
    if not key or not endpoint:
        log("FlixPatrol: API 키/엔드포인트 없음 → 일간 트렌드 생략")
        return None
    try:
        r = requests.get(endpoint, headers={**UA, "Authorization": f"Bearer {key}"}, timeout=60)
        r.raise_for_status()
        payload = r.json()
        rows = payload.get("data", payload) if isinstance(payload, dict) else payload
        items = [m for m in (_map_flixpatrol_row(x) for x in rows) if m]
        return {"date": datetime.now(timezone.utc).date().isoformat(), "items": items[:20]}
    except Exception as e:  # 보조 자료이므로 실패해도 전체 파이프라인은 계속
        log(f"FlixPatrol 실패(무시하고 계속): {e}")
        return None


def _map_flixpatrol_row(x: dict) -> dict | None:
    """FlixPatrol API 응답 1건 → 앱 공통 형식. 실제 필드명은 API 문서를 보고 맞춘다."""
    title = x.get("title") or x.get("name")
    rank = x.get("ranking") or x.get("rank")
    if not title or rank is None:
        return None
    return {
        "rank": int(rank),
        "show_title": title,
        "type": "tv" if str(x.get("type", "")).lower() in ("tv", "show", "tv show") else "movie",
        "rank_change": x.get("rankingLast") and int(x["rankingLast"]) - int(rank),
    }


# ---------------------------------------------------------------------------
# 3) TMDB 보강 — 한국어 제목, 공식 줄거리, 장르, 출연, 포스터
#    AI 가 제목만 보고 줄거리를 '지어내는' 것을 막는 사실 근거 역할
# ---------------------------------------------------------------------------
def _tmdb(path: str, **params) -> dict:
    """TMDB 호출. 짧은 'API Key'(32자리)와 긴 'API 읽기 액세스 토큰' 둘 다 지원."""
    headers = dict(UA)
    if len(TMDB_KEY) > 40:  # 읽기 액세스 토큰(Bearer)
        headers["Authorization"] = f"Bearer {TMDB_KEY}"
    else:
        params["api_key"] = TMDB_KEY
    r = requests.get(f"https://api.themoviedb.org/3/{path}", params=params, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


def tmdb_enrich(item: dict, cache: dict) -> dict:
    key = title_key(item["show_title"], None)
    if key in cache:
        return cache[key]
    if not TMDB_KEY:
        return {}
    kind = item["type"]
    try:
        # 넷플릭스 표기 제목은 영어이므로 영어로 검색해 '제목 정확 일치'를 우선하고,
        # 그다음 인기도(popularity)가 높은 작품을 고른다. (첫 결과를 무조건 쓰면 동명 다큐 등이 잡힘)
        s = _tmdb(f"search/{kind}", **{"query": item["show_title"], "language": "en-US"})
        results = s.get("results") or []
        if not results:
            cache[key] = {}
            return {}
        q = item["show_title"].strip().lower()

        def score(r):
            names = {(r.get(f) or "").strip().lower() for f in ("title", "name", "original_title", "original_name")}
            return (q in names, r.get("popularity") or 0)

        best = max(results, key=score)
        d = _tmdb(f"{kind}/{best['id']}", **{"language": "ko-KR", "append_to_response": "credits"})
        overview = d.get("overview") or ""
        if not overview:  # 한국어 줄거리가 없으면 영어 줄거리를 근거로 사용
            en = _tmdb(f"{kind}/{best['id']}", **{"language": "en-US"})
            overview = en.get("overview") or ""
        info = {
            "tmdb_id": best["id"],
            "title_ko": d.get("title") or d.get("name"),
            "original_title": d.get("original_title") or d.get("original_name"),
            "year": (d.get("release_date") or d.get("first_air_date") or "")[:4],
            "genres": [g["name"] for g in d.get("genres", [])],
            "overview_source": overview,
            "cast": [c["name"] for c in d.get("credits", {}).get("cast", [])[:5]],
            "poster": TMDB_IMG + d["poster_path"] if d.get("poster_path") else None,
            "backdrop": TMDB_IMG + d["backdrop_path"] if d.get("backdrop_path") else None,
            "vote": d.get("vote_average"),
        }
        cache[key] = info
        time.sleep(0.25)  # TMDB 요청 속도 제한 배려
        return info
    except Exception as e:
        log(f"TMDB 실패 {item['show_title']}: {e}")
        return {}


# ---------------------------------------------------------------------------
# 4) Claude — 한국어 줄거리 / 스포일러 없는 감상 포인트 / 추천 이유
# ---------------------------------------------------------------------------
AI_SCHEMA = {
    "type": "object",
    "properties": {
        "synopsis_ko": {"type": "string", "description": "한국어 줄거리 3~4문장, 결말·반전 언급 금지"},
        "watch_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": "스포일러 없는 감상 포인트 3개, 각 1문장",
        },
        "recommend_reason": {"type": "string", "description": "이런 분께 추천 + 이유, 2문장"},
        "recommend_for": {
            "type": "array",
            "items": {"type": "string"},
            "description": "추천 대상 태그 2~3개 (예: '가족과 함께', '스릴러 마니아')",
        },
        "mood_tags": {"type": "array", "items": {"type": "string"}, "description": "분위기 태그 2~3개"},
        "confidence": {
            "type": "string",
            "enum": ["high", "low"],
            "description": "근거 자료가 충분하면 high, 제목 외 정보가 거의 없으면 low",
        },
    },
    "required": ["synopsis_ko", "watch_points", "recommend_reason", "recommend_for", "mood_tags", "confidence"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """당신은 넷플릭스 작품을 한국 시청자에게 소개하는 큐레이터입니다.

규칙
1. 아래 '근거 자료'에 있는 사실만 사용합니다. 자료에 없는 인물·사건·설정을 지어내지 않습니다.
   자료가 부족하면 짧고 일반적으로 쓰고 confidence 를 "low" 로 표시합니다.
2. 스포일러 금지: 결말, 반전, 범인, 인물의 죽음, 후반부 전개는 절대 쓰지 않습니다.
   도입부 설정(첫 20% 이내)까지만 다룹니다.
3. 순위 데이터(몇 주째 TOP10, 시청수)는 추천 이유에 자연스럽게 활용해도 됩니다.
4. 자연스러운 한국어 존댓말, 과장된 홍보 문구("역대급", "필람") 금지.
"""


def ai_generate(client, item: dict, info: dict) -> dict | None:
    facts = {
        "넷플릭스 표기 제목": item["show_title"],
        "시즌": item.get("season_title"),
        "구분": "시리즈" if item["type"] == "tv" else "영화",
        "한국어 제목": info.get("title_ko"),
        "원제": info.get("original_title"),
        "공개 연도": info.get("year"),
        "장르": info.get("genres"),
        "주요 출연": info.get("cast"),
        "공식 줄거리(원문)": info.get("overview_source"),
        "TOP10 진입 주 수": item.get("weeks_in_top10"),
        "주간 시청수(글로벌)": item.get("weekly_views"),
    }
    facts = {k: v for k, v in facts.items() if v not in (None, "", [])}
    try:
        resp = client.beta.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4000,
            betas=["server-side-fallback-2026-07-01"],
            # 안전 필터가 거절하면 서버가 다른 모델로 자동 재시도 (SDK 버전과 무관하게 전달)
            extra_body={"fallbacks": "default"},
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": AI_SCHEMA}},
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": "근거 자료:\n" + json.dumps(facts, ensure_ascii=False, indent=2)
                    + "\n\n위 작품의 한국어 소개를 작성해 주세요.",
                }
            ],
        )
    except Exception as e:
        log(f"Claude 호출 실패 {item['show_title']}: {e}")
        return None
    if resp.stop_reason in ("refusal", "max_tokens"):
        log(f"Claude 응답 불완전({resp.stop_reason}) {item['show_title']}")
        return None
    text = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log(f"JSON 해석 실패 {item['show_title']}")
        return None
    data["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data["model"] = resp.model
    return data


# ---------------------------------------------------------------------------
# 5) 조립 & 저장
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-ai", action="store_true", help="AI 생성 생략(테스트)")
    args = ap.parse_args()

    tmdb_cache = load_json(TMDB_CACHE_FILE, {})
    old_tmdb = load_json(OLD_TMDB_CACHE_FILE, {})
    ai_cache = load_json(AI_CACHE_FILE, {})

    log("Tudum 글로벌 TOP10 수집")
    g_week, global_items = fetch_tudum_global()
    log(f"  → {g_week} 주, {len(global_items)}건")
    log(f"Tudum 국가별 TOP10 수집 ({COUNTRY})")
    c_week, country_items = fetch_tudum_country(COUNTRY)
    log(f"  → {c_week} 주, {len(country_items)}건")
    daily = fetch_flixpatrol_daily()

    client = None
    if not args.no_ai:
        if not os.getenv("ANTHROPIC_API_KEY"):
            log("ANTHROPIC_API_KEY 없음 → AI 해설 생략")
        else:
            import anthropic

            client = anthropic.Anthropic()

    # 글로벌 시청수를 한국 목록에도 붙여 주기 위한 색인
    global_index = {title_key(i["show_title"], i["season_title"]): i for i in global_items}

    titles: dict[str, dict] = {}
    all_items = country_items + global_items + (daily["items"] if daily else [])
    new_ai = 0
    for item in all_items:
        k = title_key(item["show_title"], item.get("season_title"))
        item["id"] = k
        if k in titles:
            continue
        g = global_index.get(k, {})
        merged = {**item, **{f: g[f] for f in ("weekly_views", "weekly_hours_viewed") if g.get(f)}}
        info = tmdb_enrich(merged, tmdb_cache)
        ai = ai_cache.get(k)
        # 자료 부족(low)으로 만든 해설은, 나중에 TMDB 줄거리가 생기면 다시 쓴다
        stale = ai is not None and ai.get("confidence") == "low" and info.get("overview_source")
        # 해설이 근거로 삼은 작품(tmdb_id)과 지금 연결된 작품이 다르면 다시 쓴다 (잘못 연결된 경우)
        if ai is not None:
            based_on = ai.get("tmdb_id", old_tmdb.get(title_key(item["show_title"], None), {}).get("tmdb_id"))
            if info.get("tmdb_id") and based_on != info["tmdb_id"]:
                stale = True
            elif info.get("tmdb_id") and "tmdb_id" not in ai:
                ai["tmdb_id"] = info["tmdb_id"]  # 같은 작품이면 기록만 남김
        if (ai is None or stale) and client is not None:
            log(f"AI 생성: {item['show_title']}")
            ai = ai_generate(client, merged, info)
            if ai:
                ai["tmdb_id"] = info.get("tmdb_id")
                ai_cache[k] = ai
                new_ai += 1
                save_json(AI_CACHE_FILE, ai_cache)  # 중간에 끊겨도 생성분 보존
        titles[k] = {
            "id": k,
            "show_title": item["show_title"],
            "season_title": item.get("season_title"),
            "type": item["type"],
            **{f: info.get(f) for f in ("title_ko", "year", "genres", "cast", "poster", "backdrop", "vote")},
            "ai": ai,
        }

    def slim(lst):
        return [
            {k: v for k, v in i.items() if k in ("id", "rank", "category", "type", "weeks_in_top10",
                                                  "weekly_views", "rank_change", "is_new", "re_entry")}
            for i in lst
        ]

    # 이번 주 급상승: 신규 진입 + 지난주보다 2계단 이상 상승 (넷플릭스 공식 데이터 기준, 무료)
    new_in = sorted([i for i in country_items if i.get("is_new") or i.get("re_entry")],
                    key=lambda x: (x.get("re_entry", False), x["rank"], x["category"]))
    risers = sorted([i for i in country_items if (i.get("rank_change") or 0) >= 2],
                    key=lambda x: (-x["rank_change"], x["rank"]))
    trending = new_in + risers

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_note": "순위: Netflix Tudum 공식 TOP10 / 작품 정보: TMDB / 해설: AI 생성",
        "country": {"code": COUNTRY, "week": c_week, "items": slim(country_items)},
        "trending": {"week": c_week, "items": slim(trending)},
        "global": {"week": g_week, "items": slim(global_items)},
        "daily": {"date": daily["date"], "items": slim(daily["items"])} if daily else None,
        "titles": titles,
    }
    save_json(OUT_DIR / "top10.json", out)
    save_json(TMDB_CACHE_FILE, tmdb_cache)
    save_json(AI_CACHE_FILE, ai_cache)
    log(f"완료: 작품 {len(titles)}개, 새 AI 해설 {new_ai}개 → output/top10.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
