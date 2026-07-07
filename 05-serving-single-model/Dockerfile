FROM python:3.12-slim AS builder
WORKDIR /build
COPY src/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY src/app.py .
EXPOSE 8000
USER 1000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]