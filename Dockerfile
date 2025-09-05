
FROM python:3.12-slim

WORKDIR /app

# System deps (optional but useful)
RUN apt-get update && apt-get install -y --no-install-recommends \
        tini \
      && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expect .env to be provided at runtime or via secrets
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "src.app"]
