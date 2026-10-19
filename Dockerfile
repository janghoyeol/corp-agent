FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY web ./web
COPY scripts ./scripts
COPY eval ./eval
COPY docker/entrypoint.sh ./entrypoint.sh

RUN pip install --no-cache-dir -e . && chmod +x entrypoint.sh

ENV PORT=8000
EXPOSE 8000

CMD ["./entrypoint.sh"]
