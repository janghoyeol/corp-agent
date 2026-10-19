#!/usr/bin/env sh
# 컨테이너 시작 시 고유번호 캐시(data/corp_codes.tsv)가 없으면 받아온 뒤
# 웹 서버를 띄운다. corp_codes.tsv는 거의 바뀌지 않는 정적 자료라
# 이미지에 포함하지 않고(용량/최신성 문제) 첫 기동 시 1회만 받는다.
set -e

if [ ! -f data/corp_codes.tsv ]; then
  echo "[entrypoint] data/corp_codes.tsv 없음 — DART에서 다운로드합니다."
  python scripts/download_corpcodes.py
fi

exec uvicorn corp_agent.api:app --host 0.0.0.0 --port "${PORT:-8000}"
