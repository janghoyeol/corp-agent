# corp-agent

> 회사명을 입력하면 **DART(전자공시시스템)** 재무제표 데이터를 조회해 매출·영업이익·
> 당기순이익 추이를 분석하고, **모든 숫자에 출처(공시 접수번호)를 붙여** 답하는
> Claude tool-use 에이전트.

```
"삼성전자 작년 영업이익 어땠어?"
"카카오 최근 3년 매출 추이 보여줘"
```

## 왜 만들었나

공공데이터 + Claude tool-use 에이전트로 만들었던 기존 프로젝트들(KOSIS 통계 질의,
국토부 실거래가 조회, 에어코리아·기상청 대기질/날씨 질의)의 설계 원칙을 **기업·재무
공시 데이터** 도메인으로 확장한 것이다. 세 프로젝트 모두 같은 뼈대를 공유한다:

> 엔티티 resolve → 공식 원자료 조회 → **계산은 코드로** → 출처와 함께 답변 → 고정
> 정답셋으로 정확도 측정

같은 설계를 얼마나 다른 도메인에 이식할 수 있는지를 보여주는 것 자체가 이 프로젝트의
포인트다. 설계 결정과 트레이드오프는 [`docs/decisions/0001-reuse-agent-pattern.md`](docs/decisions/0001-reuse-agent-pattern.md)에 ADR로 남겼다.

## 아키텍처

```
사용자 질문
   │  "삼성전자 작년 영업이익 어땠어?"
   ▼
┌─────────────────────────────────────────────────────────────┐
│  CorpAgent (Claude tool-use 루프, agent.py)                  │
│                                                               │
│   resolve_company("삼성전자")                                │
│        └─ data/corp_codes.tsv (캐싱된 DART 고유번호 전체자료) │
│           에서 후보 검색, 상장사 우선 정렬                     │
│                                                               │
│   get_financials(corp_code, bsns_year)                       │
│        └─ DART fnlttSinglAcntAll.json 호출 (CFS 우선 시도)   │
│           status 013(데이터 없음) → OFS로 자동 폴백            │
│           계정과목 표기 변형(예: "매출액" vs "수익(매출액)")   │
│           매칭 → 못 찾으면 null (지어내지 않음)                │
│                                                               │
│   compute_growth(values)                                     │
│        └─ 전년 대비 증감률을 코드로 계산 (모델 암산 금지)      │
└─────────────────────────────────────────────────────────────┘
   │
   ▼
답변 + 출처(보고서 종류 · 사업연도 · 연결/개별 여부 · 접수번호)
   + 도구 호출 로그 (--show-calls)
```

## 핵심 설계 원칙

| 원칙 | 구현 |
|---|---|
| 출처 없는 숫자는 없다 | `get_financials` 응답에 항상 `rcept_no`(접수번호)·`fs_div`(연결/개별)를 포함, 시스템 프롬프트가 답변에 출처를 강제 |
| 계산은 코드로 | 증감률은 `compute_growth`에서만 계산. 모델이 직접 암산한 숫자는 쓰지 않도록 시스템 프롬프트에 명시 |
| 모르면 모른다고 | 계정과목을 못 찾으면 `null` — 숫자를 지어내지 않음. `eval/cases.json`도 같은 원칙으로, 미검증 정답(`expected_amount: null`)은 SKIP 처리 |
| 공시 시차 인지 | "최근 사업연도"는 공시 시차(사업보고서는 결산 후 약 3개월 뒤 공시) 때문에 생각보다 과거일 수 있음 — KST 고정 날짜 계산으로 보수적 힌트 제공, 실제 존재 여부는 API 응답으로 재확인 |
| CFS→OFS 폴백 | 연결대상 자회사가 없는 회사는 연결재무제표(CFS) 조회 시 무조건 013(데이터 없음) → 개별재무제표(OFS)로 자동 재시도 |

## 디렉토리 구조

```
corp-agent/
├── src/corp_agent/
│   ├── dart_client.py   # OpenDART HTTP 클라이언트 (상태 코드 처리)
│   ├── corp_codes.py    # 고유번호 캐싱/파싱, 회사명 → corp_code 변환
│   ├── tools.py          # 3개 tool의 실제 로직 (계정과목 매칭, 증감률 계산)
│   ├── agent.py          # Claude tool-use 루프, 시스템 프롬프트
│   └── cli.py             # CLI 엔트리포인트
├── scripts/download_corpcodes.py  # 고유번호 전체자료 → data/corp_codes.tsv 캐싱
├── eval/
│   ├── cases.json         # 고정 정답셋 (expected_amount는 실 공시로 직접 검증 필요)
│   └── run_eval.py
├── tests/                  # 전부 네트워크 없이 mock으로 동작
├── docs/decisions/         # ADR
└── .github/workflows/ci.yml
```

## 빠른 시작

```bash
# 1. 설치
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. API 키 준비
cp .env.example .env
# .env에 OPENDART_API_KEY(opendart.fss.or.kr, 가입 후 즉시 발급), ANTHROPIC_API_KEY 입력

# 3. 고유번호 전체자료 캐싱 (최초 1회, 이후 거의 재다운로드 불필요)
python scripts/download_corpcodes.py

# 4. 질의
python -m corp_agent "삼성전자 2023년 영업이익 알려줘" --show-calls
```

## 테스트

```bash
pytest -q
```

모든 테스트는 `DartClient`를 mock으로 대체해 네트워크 없이 동작한다 — CFS→OFS 폴백,
계정과목 별칭 매칭, BS/IS 오매칭 방지, 증감률 계산(0으로 나누기 포함) 등 핵심 분기를
검증한다.

## Eval

```bash
OPENDART_API_KEY=... python eval/run_eval.py
```

DART 공시는 한 번 등록되면 바뀌지 않는 "확정 데이터"라서, 과거 확정 사업연도 기준
고정 정답셋으로 정확도를 측정할 수 있다. `eval/cases.json`의 `expected_amount`는
의도적으로 비워 뒀다 — 실제 DART 공시와 직접 대조해 채운 값만 정답으로 쓴다는 원칙을
eval 자체에도 적용한 것이다. 비어 있는 case는 FAIL이 아니라 SKIP으로 표시된다.

## 알려진 제약 / 리스크

- **계정과목 표기 변형**: 업종·회사마다 `account_nm` 표기가 달라(예: "매출액" vs
  "수익(매출액)") 허용 표기 목록 방식으로 처리했다. 초반엔 대형 상장사 위주로 검증 범위를
  좁히는 게 안전하다.
- **공시 호출 한도**: 일일 API 호출 한도가 있어 개발 중 반복 호출 시 빠르게 소진될 수
  있다. 현재 캐시는 고유번호 전체자료에만 적용돼 있고, 재무제표 응답 캐시(TTL)는 다음
  단계 과제다.
- **배포 환경 시간대**: "최근 사업연도" 판단에 날짜 계산이 들어가므로, 서버 시간대가
  UTC인 환경에서 깨지지 않도록 KST(`Asia/Seoul`)로 고정했다. 실제 배포 후 재검증이
  필요하다.

## 관련 프로젝트

같은 "공공데이터 + Claude tool-use 에이전트 + 코드로 계산 + 출처 명시 + 고정 정답
eval" 설계를 사용한 자매 프로젝트: stat-agent(KOSIS 통계), realty-agent(국토부
실거래가), air-agent(에어코리아/기상청).
