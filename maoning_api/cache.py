import json

import redis


_client = None


def get_redis_client(config):
    global _client
    if _client is None:
        _client = redis.Redis(
            host=config["REDIS_HOST"],
            port=config["REDIS_PORT"],
            db=config["REDIS_DB"],
            socket_connect_timeout=config["REDIS_CONNECT_TIMEOUT"],
            socket_timeout=config["REDIS_SOCKET_TIMEOUT"],
            decode_responses=True,
        )
    return _client


def get_json(config, key):
    try:
        payload = get_redis_client(config).get(key)
        if payload is None:
            return None
        return json.loads(payload)
    except (redis.RedisError, ValueError, TypeError):
        return None


def set_json(config, key, value, ttl):
    try:
        get_redis_client(config).setex(
            key,
            ttl,
            json.dumps(value, ensure_ascii=False, separators=(",", ":")),
        )
    except (redis.RedisError, TypeError, ValueError):
        return


def delete_pattern(config, pattern):
    try:
        client = get_redis_client(config)
        keys = list(client.scan_iter(match=pattern, count=100))
        if keys:
            client.delete(*keys)
    except redis.RedisError:
        return
