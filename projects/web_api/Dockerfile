FROM python:3.10-slim-bookworm AS base

WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1


FROM base AS build

# Update the package list and install necessary packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Build Python dependencies
COPY requirements.txt .
RUN python -m venv /app/venv && \
    . /app/venv/bin/activate && \
    pip install -r requirements.txt 
#     pip uninstall -y paddlepaddle && \
#     pip install -i https://www.paddlepaddle.org.cn/packages/stable/cu118/ \
#         paddlepaddle-gpu==3.0.0rc1

# Download models
COPY download_models.py .
RUN chmod +x download_models.py && . /app/venv/bin/activate && \
   /app/venv/bin/python ./download_models.py


FROM base AS prod

# Copy Python dependencies and models from the build stage
COPY --from=build /app/venv /app/venv
COPY --from=build /root/.cache/modelscope/hub/models/opendatalab/PDF-Extract-Kit-1___0/models  /opt/models
COPY --from=build /root/.cache/modelscope/hub/models/ppaanngggg/layoutreader  /opt/layoutreader

# Update the package list and install necessary packages
# 使用阿里云镜像源
RUN sed -i 's@deb.debian.org@mirrors.aliyun.com@g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's@security.debian.org@mirrors.aliyun.com@g' /etc/apt/sources.list.d/debian.sources

# 安装系统依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libgomp1 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create volume for paddleocr models
# RUN mkdir -p /root/.paddleocr
# VOLUME [ "/root/.paddleocr" ]

# Copy the app and its configuration file
COPY entrypoint.sh /app/entrypoint.sh
# 保证 entrypoint.sh 是 linux 格式
RUN sed -i 's/\r$//' /app/entrypoint.sh && \
    chmod +x /app/entrypoint.sh
COPY magic-pdf.json /root/magic-pdf.json
COPY app.py /app/app.py

# Expose the port that FastAPI will run on
EXPOSE 8000

# Command to run FastAPI using Uvicorn, pointing to app.py and binding to 0.0.0.0:8000
ENTRYPOINT [ "/app/entrypoint.sh" ]
CMD ["--host", "0.0.0.0", "--port", "8000"]

FROM prod AS prod_with_img2pdf

WORKDIR /app

## python 环境 一个 img2pdf
RUN python -m venv /app/venv && \
    . /app/venv/bin/activate && \
    pip install img2pdf 
    # -i https://mirrors.aliyun.com/pypi/simple/

## 安装soffice
#RUN sed -i 's@deb.debian.org@mirrors.aliyun.com@g' /etc/apt/sources.list.d/debian.sources
RUN apt-get update && \
    apt-get install -y --no-install-recommends libreoffice && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy the app and its configuration file
COPY entrypoint.sh /app/entrypoint.sh
# 保证 entrypoint.sh 是 linux 格式
RUN sed -i 's/\r$//' /app/entrypoint.sh && \
    chmod +x /app/entrypoint.sh
COPY magic-pdf.json /root/magic-pdf.json
COPY app.py /app/app.py

# Expose the port that FastAPI will run on
EXPOSE 8000

# Command to run FastAPI using Uvicorn, pointing to app.py and binding to 0.0.0.0:8000
ENTRYPOINT [ "/app/entrypoint.sh" ]
CMD ["--host", "0.0.0.0", "--port", "8000"]

