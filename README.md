# NJY_MaoNing_Be

猫宁平台独立后端，整合了药渣回收、猫砂出售和猫砂试用三个模块。

## 本地启动

需要可访问的 MySQL、MinIO 和 Redis。

```bash
pip install -r requirements.txt
gunicorn --bind 0.0.0.0:5000 app:app
```

## K8s 资源

- `k8s/namespace.yaml` 创建 `maoning` 命名空间
- `k8s/mysql*.yaml` 部署 MySQL 并初始化表结构
- `k8s/minio.yaml` 部署 MinIO 对象存储
- `k8s/redis.yaml` 部署 Redis 缓存服务
- `k8s/api*.yaml` 部署统一 API 服务
- `k8s/ingress.yaml` 通过集群现有 `nginx` ingress 暴露服务
- `k8s/persistent-volumes.yaml` 为 `local-storage` 集群补齐 Maoning 所需 PV
- `k8s/default-maoning-api-proxy.yaml` 在 `default` namespace 创建公网入口代理 Service
- `k8s/default-backend-server-ingress.yaml` 恢复原有老接口路由，并新增 `/maoning` 前缀给新的独立后端
- `k8s/default-maoning-minio-proxy.yaml` 在 `default` namespace 创建 maoning MinIO 代理 Service
- `k8s/default-maoning-minio-public-ingress.yaml` 通过 `www.njwjxy.cn` 将 `/maoning-public-assets` 直连到 maoning MinIO

`k8s/api.yaml` 现改为只使用开源镜像：

- `alpine/git` 作为 initContainer 拉取当前 GitHub 仓库代码
- `python:3.11-slim` 作为运行容器安装依赖并启动 Flask/Gunicorn

## Redis 缓存

后端使用 Redis 作为旁路缓存，降低高频读取接口对 MySQL 的压力。Redis 不可用时会自动跳过缓存并回退到 MySQL 查询，避免缓存故障影响业务接口。

已缓存的主要接口：

- 个人信息和用户列表
- 反馈列表、反馈统计、消极问题 TOP5
- 药渣回收列表、详情、统计汇总、按单位统计详情
- 猫砂出售列表
- 猫砂试用列表和详情

默认过期时间：

- `CACHE_SHORT_TTL=30`：反馈统计等变化较快的数据
- `CACHE_DEFAULT_TTL=60`：用户、药渣、试用等常规数据
- `CACHE_LONG_TTL=120`：猫砂出售、药渣统计等聚合或较稳定数据

写入、更新、审批和反馈 AI 分析回写成功后，会按业务维度主动清理相关缓存。接口响应头会返回 `X-Cache: HIT` 或 `X-Cache: MISS`，用于排查缓存命中情况。

相关环境变量：

- `REDIS_HOST`，默认 `redis`
- `REDIS_PORT`，默认 `6379`
- `REDIS_DB`，默认 `0`
- `REDIS_CONNECT_TIMEOUT`，默认 `0.3`
- `REDIS_SOCKET_TIMEOUT`，默认 `0.5`
- `CACHE_SHORT_TTL`，默认 `30`
- `CACHE_DEFAULT_TTL`，默认 `60`
- `CACHE_LONG_TTL`，默认 `120`

K8s 部署或更新缓存服务：

```bash
kubectl apply -f k8s/redis.yaml
kubectl apply -f k8s/api-configmap.yaml
kubectl rollout restart deployment/maoning-api -n maoning
```

## MinIO

新的独立小程序对象存储使用 `maoning` namespace 下的 MinIO：

- API 外部入口：`http://<node-ip>:30900`
- Console 外部入口：`http://<node-ip>:30901`
- 小程序内静态资源推荐通过 `https://www.njwjxy.cn:30443/maoning-public-assets/...` 访问
