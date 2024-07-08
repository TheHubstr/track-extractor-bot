# build like: docker build . -t tstripbot:latest -t tstripbot:1.1
ARG PYTHON_VERSION=3.12.4
FROM python:${PYTHON_VERSION}-slim AS base

# Prevents Python from writing pyc files.
ENV PYTHONDONTWRITEBYTECODE=1

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# add deps for secp256k1 and curl for healthcheck
RUN apt update && apt install -y pkg-config
RUN apt install -y build-essential
RUN apt install -y curl


ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/nonexistent" \
    --shell "/sbin/nologin" \
    --no-create-home \
    --uid "${UID}" \
    appuser


RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    python -m pip install -r requirements.txt

# Switch to the non-privileged user to run the application.
USER appuser
COPY . .
CMD python3 main.py
