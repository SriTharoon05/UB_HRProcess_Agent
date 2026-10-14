FROM python:3.12-slim
WORKDIR /app
RUN --mount=type=secret,id=build_ca_bundle \
    if [ -f /run/secrets/build_ca_bundle ]; then export PIP_CERT=/run/secrets/build_ca_bundle; fi; \
    pip install --no-cache-dir uv==0.12.23
COPY pyproject.toml uv.lock ./
RUN --mount=type=secret,id=build_ca_bundle \
    if [ -f /run/secrets/build_ca_bundle ]; then export SSL_CERT_FILE=/run/secrets/build_ca_bundle; fi; \
    uv sync --frozen --no-dev --no-install-project
COPY app ./app
RUN useradd --uid 10001 --create-home talentmatch && mkdir -p /app/data/resumes && chown -R talentmatch:talentmatch /app/data /app/app
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SQLITE_DATABASE_PATH=/app/data/talentmatch.sqlite3
USER talentmatch
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
