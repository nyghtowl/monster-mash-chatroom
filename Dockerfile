# syntax=docker/dockerfile:1.5
FROM python:3.11-slim as base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --upgrade pip \
    && pip install -e .

EXPOSE 8000

CMD ["uvicorn", "monster_mash_chatroom.app:app", "--host", "0.0.0.0", "--port", "8000"]
