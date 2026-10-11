# ---------- 依赖构建阶段 ----------
FROM python:3.12-slim-bookworm AS deps

# 编译工具仅在需要从源码构建无轮子的包时使用
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --prefix=/opt/venv -r /tmp/requirements.txt

# ---------- 运行阶段 ----------
FROM python:3.12-slim-bookworm AS runtime

ARG GIT_COMMIT=""
ARG VERSION=""

# 运行期系统依赖:
# - ffmpeg: 语音、贴纸转换
# - ca-certificates: HTTPS 证书信任
# - curl: 容器健康检查
# - tzdata: 时区支持
# - gosu: 安全降权以非 root 用户运行
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        ffmpeg \
        tzdata \
        gosu \
    && rm -rf /var/lib/apt/lists/*

# 环境变量配置:
# - PYTHONUNBUFFERED=1: 实时输出日志，避免 docker logs 缓冲滞后
# - TQSYNC_CONTAINER=1: 标记容器环境，跳过不可用的进程内更新与配置写盘
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/opt/venv/lib/python3.12/site-packages \
    TQSYNC_CONTAINER=1 \
    TZ=Asia/Shanghai \
    TQSYNC_COMMIT=${GIT_COMMIT} \
    TQSYNC_VERSION=${VERSION}

# 从依赖阶段复制已安装的 Python 包
COPY --from=deps /opt/venv /opt/venv

WORKDIR /app

# 创建专用运行用户 (UID/GID 1000)
RUN groupadd -g 1000 tqsync && \
    useradd -u 1000 -g tqsync -s /bin/sh -d /app tqsync

# 复制项目源码
COPY . .

# 内嵌构建元数据并初始化目录权限
RUN if [ -n "$GIT_COMMIT" ]; then echo "$GIT_COMMIT" > /app/.commit; fi && \
    chmod +x /app/docker-entrypoint.sh && \
    mkdir -p /app/db /app/logs /app/temp /app/plugins && \
    chown -R tqsync:tqsync /app

EXPOSE 8080 8081

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://127.0.0.1:8081/health || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "main.py"]
