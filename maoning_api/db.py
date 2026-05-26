from datetime import date, datetime
from decimal import Decimal

import pymysql
from pymysql.cursors import DictCursor


SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS recycle_records (
      id INT NOT NULL AUTO_INCREMENT,
      user_openid VARCHAR(64) DEFAULT NULL,
      unit VARCHAR(128) NOT NULL,
      contact VARCHAR(64) NOT NULL,
      date DATE NOT NULL,
      location VARCHAR(255) NOT NULL,
      weight DECIMAL(10, 2) NOT NULL,
      herbs VARCHAR(255) DEFAULT '',
      type ENUM('company', 'person') NOT NULL DEFAULT 'company',
      state ENUM('pending', 'finish') NOT NULL DEFAULT 'pending',
      approved_weight DECIMAL(10, 2) DEFAULT NULL,
      batch_no VARCHAR(64) DEFAULT NULL,
      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      KEY idx_recycle_user_openid (user_openid),
      KEY idx_recycle_user_type_created (user_openid, type, created_at),
      KEY idx_recycle_type_created (type, created_at),
      KEY idx_recycle_state_type_unit_location (state, type, unit, location),
      KEY idx_recycle_state_unit_location_date (state, unit, location, date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS products (
      id INT NOT NULL AUTO_INCREMENT,
      image_key VARCHAR(255) DEFAULT NULL,
      erweiimage_key VARCHAR(255) DEFAULT NULL,
      ywymimage_key VARCHAR(255) DEFAULT NULL,
      spec VARCHAR(128) NOT NULL,
      price VARCHAR(64) NOT NULL,
      location VARCHAR(255) NOT NULL,
      phone VARCHAR(64) NOT NULL,
      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_profiles (
      openid VARCHAR(64) NOT NULL,
      nickname VARCHAR(128) NOT NULL DEFAULT '微信用户',
      email VARCHAR(191) NOT NULL DEFAULT '',
      avatar_key VARCHAR(255) DEFAULT NULL,
      user_type ENUM('普通用户', '管理员', '超级管理员') NOT NULL DEFAULT '普通用户',
      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (openid),
      KEY idx_user_type (user_type),
      KEY idx_user_updated_created (updated_at, created_at)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_feedbacks (
      id BIGINT NOT NULL AUTO_INCREMENT,
      user_openid VARCHAR(64) NOT NULL,
      nickname_snapshot VARCHAR(128) NOT NULL DEFAULT '',
      email_snapshot VARCHAR(191) NOT NULL DEFAULT '',
      content TEXT NOT NULL,
      sentiment ENUM('积极', '消极') NOT NULL DEFAULT '积极',
      problem_category VARCHAR(32) NOT NULL DEFAULT '其他问题',
      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      KEY idx_feedback_user_openid (user_openid),
      KEY idx_feedback_created (created_at),
      KEY idx_feedback_sentiment_category (sentiment, problem_category)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS maosha_shiyong (
      id INT NOT NULL AUTO_INCREMENT,
      user_openid VARCHAR(64) DEFAULT NULL,
      image_key VARCHAR(255) NOT NULL,
      name VARCHAR(128) NOT NULL,
      phone VARCHAR(64) NOT NULL,
      status ENUM('pending', 'approve') NOT NULL DEFAULT 'pending',
      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      KEY idx_maosha_shiyong_user_openid (user_openid),
      KEY idx_maosha_shiyong_user_id (user_openid, id)
    )
    """,
]


INDEX_STATEMENTS = [
    (
        "recycle_records",
        "idx_recycle_user_type_created",
        "ALTER TABLE recycle_records ADD KEY idx_recycle_user_type_created (user_openid, type, created_at)",
    ),
    (
        "recycle_records",
        "idx_recycle_type_created",
        "ALTER TABLE recycle_records ADD KEY idx_recycle_type_created (type, created_at)",
    ),
    (
        "recycle_records",
        "idx_recycle_state_type_unit_location",
        "ALTER TABLE recycle_records ADD KEY idx_recycle_state_type_unit_location (state, type, unit, location)",
    ),
    (
        "recycle_records",
        "idx_recycle_state_unit_location_date",
        "ALTER TABLE recycle_records ADD KEY idx_recycle_state_unit_location_date (state, unit, location, date)",
    ),
    (
        "user_profiles",
        "idx_user_type",
        "ALTER TABLE user_profiles ADD KEY idx_user_type (user_type)",
    ),
    (
        "user_profiles",
        "idx_user_updated_created",
        "ALTER TABLE user_profiles ADD KEY idx_user_updated_created (updated_at, created_at)",
    ),
    (
        "user_feedbacks",
        "idx_feedback_created",
        "ALTER TABLE user_feedbacks ADD KEY idx_feedback_created (created_at)",
    ),
    (
        "user_feedbacks",
        "idx_feedback_sentiment_category",
        "ALTER TABLE user_feedbacks ADD KEY idx_feedback_sentiment_category (sentiment, problem_category)",
    ),
    (
        "maosha_shiyong",
        "idx_maosha_shiyong_user_id",
        "ALTER TABLE maosha_shiyong ADD KEY idx_maosha_shiyong_user_id (user_openid, id)",
    ),
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
    if isinstance(value, (date, datetime)):
        return value.isoformat()
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
            cursor.execute("SHOW COLUMNS FROM recycle_records LIKE 'user_openid'")
            if not cursor.fetchone():
                cursor.execute(
                    """
                    ALTER TABLE recycle_records
                    ADD COLUMN user_openid VARCHAR(64) DEFAULT NULL AFTER id
                    """
                )
            cursor.execute("SHOW INDEX FROM recycle_records WHERE Key_name = 'idx_recycle_user_openid'")
            if not cursor.fetchone():
                cursor.execute(
                    """
                    ALTER TABLE recycle_records
                    ADD KEY idx_recycle_user_openid (user_openid)
                    """
                )
            cursor.execute("SHOW COLUMNS FROM maosha_shiyong LIKE 'user_openid'")
            if not cursor.fetchone():
                cursor.execute(
                    """
                    ALTER TABLE maosha_shiyong
                    ADD COLUMN user_openid VARCHAR(64) DEFAULT NULL AFTER id
                    """
                )
            cursor.execute("SHOW INDEX FROM maosha_shiyong WHERE Key_name = 'idx_maosha_shiyong_user_openid'")
            if not cursor.fetchone():
                cursor.execute(
                    """
                    ALTER TABLE maosha_shiyong
                    ADD KEY idx_maosha_shiyong_user_openid (user_openid)
                    """
                )
            cursor.execute("SHOW COLUMNS FROM user_feedbacks LIKE 'sentiment'")
            if not cursor.fetchone():
                cursor.execute(
                    """
                    ALTER TABLE user_feedbacks
                    ADD COLUMN sentiment ENUM('积极', '消极') NOT NULL DEFAULT '积极' AFTER content
                    """
                )
            cursor.execute("SHOW COLUMNS FROM user_feedbacks LIKE 'problem_category'")
            if not cursor.fetchone():
                cursor.execute(
                    """
                    ALTER TABLE user_feedbacks
                    ADD COLUMN problem_category VARCHAR(32) NOT NULL DEFAULT '其他问题' AFTER sentiment
                    """
                )
            cursor.execute(
                """
                UPDATE user_profiles
                SET user_type = '超级管理员'
                WHERE user_type = '高级管理员'
                """
            )
            cursor.execute(
                """
                ALTER TABLE user_profiles
                MODIFY user_type ENUM('普通用户', '管理员', '超级管理员')
                NOT NULL DEFAULT '普通用户'
                """
            )
            cursor.execute("SELECT 1 FROM user_profiles WHERE user_type = '超级管理员' LIMIT 1")
            if not cursor.fetchone():
                cursor.execute(
                    """
                    UPDATE user_profiles
                    SET user_type = '超级管理员'
                    WHERE user_type = '管理员'
                    ORDER BY created_at ASC
                    LIMIT 1
                    """
                )
            for table_name, index_name, statement in INDEX_STATEMENTS:
                cursor.execute(
                    "SHOW INDEX FROM `{}` WHERE Key_name = %s".format(table_name),
                    (index_name,),
                )
                if not cursor.fetchone():
                    try:
                        cursor.execute(statement)
                    except pymysql.err.OperationalError as exc:
                        if exc.args[0] != 1061:
                            raise
        conn.commit()
    finally:
        conn.close()
