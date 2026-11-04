# Backend image. Works on any Docker host; defaults suit a free Hugging Face Docker Space
# (port 7860, non-root user 1000, writable /tmp).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    BEFREE_DATA_DIR=/tmp/befree PORT=7860 OMP_NUM_THREADS=2

# tesseract is the optional fallback OCR engine; libgl/glib are needed by OpenCV/ONNX wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY samples ./samples
COPY scripts ./scripts

# Download the OCR models at build time so the first scanned upload isn't slow,
# and make sure the bundled classifier loads with the installed scikit-learn.
RUN python -c "from rapidocr import RapidOCR; RapidOCR()" \
 && python -c "import sys; sys.path.insert(0,'.'); from app.classify.ml import get_model; print(get_model().card['holdout'])" \
 && useradd -m -u 1000 user && chown -R user /app

USER user
EXPOSE 7860
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers"]
