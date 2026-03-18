FROM python:3.10-slim

WORKDIR /app

# 安装系统级构建依赖
RUN apt-get update && apt-get install -y \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

# 先安装基础依赖（加速后续安装）
RUN pip install --no-cache-dir fastapi uvicorn httpx

# 拷贝 PyRIT 项目（注意大写 PyRIT 目录名，Linux 区分大小写）
COPY ./PyRIT /app/PyRIT

# 从 pyproject.toml 安装 pyrit 及其所有依赖
RUN pip install --no-cache-dir /app/PyRIT

# 把 bridge_api.py 放到工作目录
COPY ./PyRIT/bridge_api.py /app/bridge_api.py

# 预创建 PyRIT 配置目录
RUN mkdir -p /root/.pyrit

# 健康检查：确认服务存活
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1

EXPOSE 5000

CMD ["python", "bridge_api.py"]
