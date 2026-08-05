# ---------- 依赖安装阶段 ----------
FROM python:3.12-slim-bookworm AS deps

# 预装依赖，便于利用构建缓存。
# 编译工具仅在需要从源码构建某些无轮子的包时使用（如 arm64 下的 rlottie-python）。
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# 预装依赖，便于利用构建缓存
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --prefix=/opt/venv -r /tmp/requirements.txt

# ---------- 运行阶段 ----------
FROM python:3.12-slim-bookworm AS runtime

# 系统依赖: git 用于构建时内嵌 commit hash; ffmpeg 用于语音/贴纸转换; tzdata 设置时区
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        ffmpeg \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

# 从依赖阶段复制已安装的 Python 包
ENV PYTHONPATH=/opt/venv/lib/python3.12/site-packages
COPY --from=deps /opt/venv /opt/venv

WORKDIR /app

COPY . .

# 非 root 运行
RUN groupadd --system tqsync && useradd --system --gid tqsync tqsync \
    && mkdir -p /app/db /app/logs /app/temp \
    && chown -R tqsync:tqsync /app
USER tqsync

EXPOSE 8080 8081

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/health', timeout=3)"

CMD ["python", "main.py"]
