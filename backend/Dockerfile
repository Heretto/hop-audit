# The full image ships git, which pip needs for hop-core's tagged release;
# the runtime image stays slim.
FROM python:3.12 AS build
COPY requirements.txt .
RUN python -m venv /venv && /venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim
COPY --from=build /venv /venv
ENV PATH=/venv/bin:$PATH
# Chromium for the Letter PDFs (report and one-sheets, pdf.py), with the
# system libraries it needs.
RUN playwright install --with-deps chromium && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . .

EXPOSE 8000
# One process: audits run as asyncio tasks in it (and the scheduler will).
# The web container's nginx (and Caddy on the VM) are on private addresses;
# trust their X-Forwarded-For / -Proto, so rate limits see the visitor and
# requests know they arrived over HTTPS.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", \
     "--forwarded-allow-ips", "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,127.0.0.1"]
