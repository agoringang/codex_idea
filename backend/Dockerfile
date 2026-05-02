FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY scripts ./scripts

RUN pip install --no-cache-dir -e .
RUN pip install --no-cache-dir google-cloud-storage

RUN mkdir -p data
COPY data/netkeiba_list_urls.txt ./data/netkeiba_list_urls.txt

CMD ["python", "scripts/netkeiba_fetch_gcs.py"]