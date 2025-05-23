# 基于MinerU的PDF解析API

- MinerU的GPU镜像构建
- 基于FastAPI的PDF解析接口

## 构建方式

```
docker build -t mineru-api .
```

或者使用代理：

```
docker build --build-arg http_proxy=http://127.0.0.1:7890 --build-arg https_proxy=http://127.0.0.1:7890 -t mineru-api .
```

## 启动命令

```
docker run --rm -it --gpus=all -p 8000:8000 mineru-api
```

## 测试参数

访问地址：

```
http://localhost:8000/docs
http://127.0.0.1:8000/docs
```

## 修改后的执行
```bash
 docker run -d --gpus all -p 10086:8000 --network docker_ssrf_proxy_network --name mineru-api-v3 -v minerupaddleocr:/root/.paddleocr mineru-api:v0.3
```

