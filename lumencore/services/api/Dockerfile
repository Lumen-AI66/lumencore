FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ARG APP_UID=10001
ARG APP_GID=10001

WORKDIR /app

RUN groupadd --gid ${APP_GID} app && \
    useradd --uid ${APP_UID} --gid ${APP_GID} --create-home --shell /usr/sbin/nologin app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app
RUN chown -R app:app /app && \
    mkdir -p /opt/lumencore/deployment && \
    chown -R app:app /opt/lumencore

USER app:app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
