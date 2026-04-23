from decimal import Decimal

import pymysql
from pymysql.cursors import DictCursor


def get_connection(config, dict_cursor=False):
    connect_kwargs = {
        host=config["MYSQL_HOST"],
        port=config["MYSQL_PORT"],
        user=config["MYSQL_USER"],
        password=config["MYSQL_PASSWORD"],
        database=config["MYSQL_DATABASE"],
        charset="utf8mb4",
        autocommit=False,
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
