# 넷플 TOP10 가이드 — 안드로이드 앱 (시제품 v1.0)

## 한눈에 보기

```
[Netflix Tudum 공식 주간 TOP10]   ← 기준 데이터 (무료 공개 파일, 매주 화요일경 갱신)
[FlixPatrol 일간 순위]            ← 보조 트렌드 (유료 API 계약 시에만)
[TMDB 작품 정보]                  ← 한국어 제목·공식 줄거리·포스터 (AI가 지어내지 않게 하는 근거)
          │
          ▼  매일 08:00 자동 실행 (GitHub Actions, 서버 비용 0원)
   server/pipeline.py ── Claude AI ──▶ 한국어 줄거리 / 스포일러 없는 감상 포인트 / 추천 이유
          │                           (작품당 1번만 생성하고 저장 → 비용 최소화)
          ▼
   top10.json (인터넷에 공개된 파일 1개)
          │
          ▼
   안드로이드 앱 ── 한국 주간 / 글로벌 주간 / 일간 트렌드 탭 → 작품 상세(AI 해설)
```

**왜 이렇게 나눴나:** API 키를 앱 안에 넣으면 누구나 빼내서 요금을 쓸 수 있습니다. 그래서 AI 호출은 서버(자동 작업)에서만 하고, 앱은 완성된 결과 파일만 읽습니다.

## 폴더 구성

| 위치 | 내용 |
|---|---|
| `server/pipeline.py` | 데이터 수집 + AI 해설 생성 스크립트 |
| `server/.env.example` | 필요한 키 목록 (복사해서 `.env`로) |
| `.github/workflows/update-top10.yml` | 매일 자동 실행 설정 |
| `android/` | 안드로이드 앱 (Kotlin + Jetpack Compose). Android Studio로 열면 됩니다 |

## 현재 상태 (2026-11-05 저녁)

- 가동 중: 매일 08:00 자동 갱신, Claude·TMDB 키 등록 완료, 55편 중 46편 충실 해설
- 대표님 폰 설치 완료. 설치 파일: https://github.com/yesieum-create/netflix-top10-app/releases (QR: `screenshots/설치_QR코드.png`)
- ⚠️ Claude 키 2026-12-05 만료 → 만료 전 교체

## 처음 확인된 것 (2026-11-05)

- Netflix Tudum 데이터 파일 실제 다운로드 성공: 최신 주 **2026-11-01**, 한국 20건 · 글로벌 40건 → 작품 55개 정리 ✅
- 안드로이드 앱 빌드 성공 (`android/app/build/outputs/apk/debug/app-debug.apk`) ✅
- **아직 안 된 것:** Claude·TMDB 키가 없어 AI 해설 실제 생성은 테스트 전 / 실제 폰·에뮬레이터 화면 확인 전

## 실행 순서 (처음 1회)

1. **키 발급** (각 5분)
   - Claude API 키: console.anthropic.com → API Keys
   - TMDB API 키: themoviedb.org 회원가입 → 설정 → API
   - (선택) FlixPatrol: flixpatrol.com/about/premium → API 플랜 (Start $9.99/월~)
2. **GitHub 저장소 만들기** → 이 `netflix-top10-app` 폴더를 올림
3. 저장소 **Settings → Secrets → Actions** 에 `ANTHROPIC_API_KEY`, `TMDB_API_KEY` 등록
4. **Settings → Pages** → 브랜치 `main`, 폴더 `/docs` 선택 → 주소 확인
   (예: `https://아이디.github.io/netflix-top10-app/top10.json`)
5. `android/app/build.gradle.kts` 의 `DATA_URL` 을 4번 주소로 교체
6. **Actions → update-top10 → Run workflow** 로 첫 데이터 생성
7. Android Studio에서 `android` 폴더 열기 → ▶ 실행 (폰 USB 연결 또는 에뮬레이터)

→ 2~7번은 Claude에게 "같이 해줘"라고 하시면 화면을 열고 한 단계씩 진행해 드립니다.

## 비용 (ESTIMATE — 실제 청구로 확인 필요)

| 항목 | 예상 |
|---|---|
| Claude (Opus 5.5) | 작품당 약 $0.05, 주 신규 15~25편 → **월 $3~5** |
| TMDB / Tudum / GitHub | 0원 (단, 상업화 시 TMDB 별도 계약) |
| FlixPatrol | 선택, 월 $9.99~ |
| 구글 플레이 개발자 등록 | 1회 $25 |

## RED FLAG — 출시 전 반드시 확인

1. **TMDB 상업 이용:** 무료 키는 비상업용만 허용. 광고·유료화하면 TMDB와 별도 계약 필요.
2. **FlixPatrol 스크래핑 금지:** 웹페이지 자동 수집은 약관 위험 → 코드는 유료 API로만 동작하게 막아 둠.
3. **Netflix 상표:** 앱 이름·아이콘에 "Netflix" 로고·빨간 N 사용 금지. 현재 이름 "넷플 TOP10 가이드"도 스토어 심사 전 재검토 권장. 앱 하단에 "Netflix와 무관한 비공식 서비스" 문구 표시 중.
4. **AI 오류:** 줄거리는 TMDB 공식 줄거리를 근거로만 쓰게 지시했고, 근거가 부족하면 "자료 적음" 표시. 그래도 출시 전 상위 20편은 사람이 한 번 검수 권장.
