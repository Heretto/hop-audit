# The full image ships git, which pip needs for hop-core's tagged release;
# the runtime image stays slim.
FROM python:3.12 AS build
COPY requirements.txt .
RUN python -m venv /venv && /venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim
COPY --from=build /venv /venv
ENV PATH=/venv/bin:$PATH
WORKDIR /app
COPY . .

EXPOSE 8000
# Single replica: the scheduler (milestone 9) runs in-process.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
