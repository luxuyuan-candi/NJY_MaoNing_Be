import os


class Config:
    MYSQL_HOST = os.getenv("MYSQL_HOST", "mysql")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "maoning")

    MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
    MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "")
    MINIO_BUCKET_MAOSHA = os.getenv("MINIO_BUCKET_MAOSHA", "cat-litter")
    MINIO_BUCKET_SHIYONG = os.getenv("MINIO_BUCKET_SHIYONG", "maosha-shiyong")
    MINIO_BUCKET_PUBLIC = os.getenv("MINIO_BUCKET_PUBLIC", "public-assets")

    WECHAT_APP_ID = os.getenv("WECHAT_APP_ID", "")
    WECHAT_APP_SECRET = os.getenv("WECHAT_APP_SECRET", "")

    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_API_BASE = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    REDIS_HOST = os.getenv("REDIS_HOST", "redis")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))
    REDIS_CONNECT_TIMEOUT = float(os.getenv("REDIS_CONNECT_TIMEOUT", "0.3"))
    REDIS_SOCKET_TIMEOUT = float(os.getenv("REDIS_SOCKET_TIMEOUT", "0.5"))
    CACHE_SHORT_TTL = int(os.getenv("CACHE_SHORT_TTL", "30"))
    CACHE_DEFAULT_TTL = int(os.getenv("CACHE_DEFAULT_TTL", "60"))
    CACHE_LONG_TTL = int(os.getenv("CACHE_LONG_TTL", "120"))
