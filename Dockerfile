FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --gid 1000 warreporter \
    && useradd --uid 1000 --gid 1000 --create-home warreporter

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=warreporter:warreporter . .
RUN mkdir -p data reports site \
    && chown -R warreporter:warreporter data reports site

USER warreporter
CMD ["python", "-m", "scripts.continuous_loop"]
