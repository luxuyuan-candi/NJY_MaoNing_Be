# NJY_MaoNing_Be

猫宁平台独立后端，整合了药渣回收、猫砂出售和猫砂试用三个模块。

## 本地启动

```bash
pip install -r requirements.txt
gunicorn --bind 0.0.0.0:5000 app:app
```

## K8s 资源

- `k8s/namespace.yaml` 创建 `maoning` 命名空间
- `k8s/mysql*.yaml` 部署 MySQL 并初始化表结构
- `k8s/minio.yaml` 部署 MinIO 对象存储
- `k8s/api*.yaml` 部署统一 API 服务
- `k8s/ingress.yaml` 通过集群现有 `nginx` ingress 暴露服务
- `k8s/persistent-volumes.yaml` 为 `local-storage` 集群补齐 Maoning 所需 PV
- `k8s/default-maoning-api-proxy.yaml` 在 `default` namespace 创建公网入口代理 Service
- `k8s/default-backend-server-ingress.yaml` 复用 `default` namespace 的 `www.njwjxy.cn` 与 `ingress-tls`

`k8s/api.yaml` 默认使用 `maoning-api:latest` 镜像，部署前需要在当前环境可访问的容器运行时中准备该镜像。
