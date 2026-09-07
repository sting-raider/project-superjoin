FROM node:22-alpine AS web-build
WORKDIR /web
COPY web/package.json ./
RUN npm install --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN useradd --create-home --uid 10001 appuser
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .
COPY app ./app
COPY demo ./demo
COPY scripts ./scripts
COPY README.md ./README.md
COPY --from=web-build /web/dist ./web/dist
RUN mkdir -p /app/data/uploads && chown -R appuser:appuser /app
USER appuser
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]

