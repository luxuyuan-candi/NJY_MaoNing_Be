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
- `k8s/default-backend-server-ingress.yaml` 恢复原有老接口路由，并新增 `/maoning` 前缀给新的独立后端

`k8s/api.yaml` 现改为只使用开源镜像：

- `alpine/git` 作为 initContainer 拉取当前 GitHub 仓库代码
- `python:3.11-slim` 作为运行容器安装依赖并启动 Flask/Gunicorn
