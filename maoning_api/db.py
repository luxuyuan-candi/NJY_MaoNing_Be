from decimal import Decimal

import pymysql
from pymysql.cursors import DictCursor


SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS user_profiles (
      openid VARCHAR(64) NOT NULL,
      nickname VARCHAR(128) NOT NULL DEFAULT '微信用户',
      email VARCHAR(191) NOT NULL DEFAULT '',
      avatar_key VARCHAR(255) DEFAULT NULL,
      user_type ENUM('普通用户', '管理员') NOT NULL DEFAULT '普通用户',
      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (openid)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_feedbacks (
      id BIGINT NOT NULL AUTO_INCREMENT,
      user_openid VARCHAR(64) NOT NULL,
      nickname_snapshot VARCHAR(128) NOT NULL DEFAULT '',
      email_snapshot VARCHAR(191) NOT NULL DEFAULT '',
      content TEXT NOT NULL,
      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      KEY idx_feedback_user_openid (user_openid)
    )
    """,
]


def get_connection(config, dict_cursor=False):
    connect_kwargs = {
        "host": config["MYSQL_HOST"],
        "port": config["MYSQL_PORT"],
        "user": config["MYSQL_USER"],
        "password": config["MYSQL_PASSWORD"],
        "database": config["MYSQL_DATABASE"],
        "charset": "utf8mb4",
        "autocommit": False,
    }
    if dict_cursor:
        connect_kwargs["cursorclass"] = DictCursor
    return pymysql.connect(**connect_kwargs)


def json_ready(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    return value


def ensure_tables(config):
    conn = get_connection(config)
    try:
        with conn.cursor() as cursor:
            for statement in SCHEMA_STATEMENTS:
                cursor.execute(statement)
        conn.commit()
    finally:
        conn.close()
