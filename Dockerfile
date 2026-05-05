# ===== Stage 1: Build frontend =====
FROM node:22-slim AS frontend-builder

RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /build
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm run build

# ===== Stage 2: Runtime =====
FROM python:3.11-slim AS runtime

# Install nginx, supervisor, and libreoffice-writer for .doc support
RUN apt-get update && \
    apt-get install -y --no-install-recommends nginx supervisor libreoffice-writer antiword catdoc && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/app/ ./app/
COPY backend/pyproject.toml .

# Download docling models (layout + table structure, ~506MB)
RUN python3 -c "from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline; StandardPdfPipeline.download_models_hf()" && \
    python3 -c "from docling.document_converter import DocumentConverter; DocumentConverter().download_models()" && \
    echo "Docling models downloaded" || echo "Model download failed (build with local models if needed)"

# Copy built frontend
COPY --from=frontend-builder /build/dist/ /app/frontend/dist/

# Nginx config
COPY nginx.conf /etc/nginx/sites-available/superdeep
RUN ln -sf /etc/nginx/sites-available/superdeep /etc/nginx/sites-enabled/superdeep && \
    rm -f /etc/nginx/sites-enabled/default

# Supervisor config
COPY supervisord.conf /etc/supervisor/conf.d/superdeep.conf

# Entrypoint
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Create data directory skeleton
RUN mkdir -p /app/data/logs /app/data/faiss /app/data/knowledge_bases /app/data/tool_outputs

EXPOSE 80
VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost/api/knowledge-bases || exit 1

ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Shanghai

WORKDIR /app
ENTRYPOINT ["/app/entrypoint.sh"]
