import json
import threading
from urllib import error, parse, request as urllib_request

from flask import jsonify, request, send_file

from .cache import delete_pattern, get_json, set_json
from .db import get_connection, json_ready
from .storage import fetch_object, upload_image


def register_routes(app):
    feedback_categories = [
        "功能异常",
        "页面体验",
        "性能卡顿",
        "账号登录",
        "数据内容",
        "反馈建议",
        "其他问题",
    ]

    def clean_text(value):
        if value is None:
            return ""
        return str(value).strip()

    def cache_key(*parts):
        escaped = [parse.quote(clean_text(part), safe="") for part in parts]
        return "maoning:" + ":".join(escaped)

    def cached_response(key, ttl, loader, success_wrapper=True):
        cached = get_json(app.config, key)
        if cached is not None:
            payload = {"success": True, "data": cached} if success_wrapper else cached
            response = jsonify(payload)
            response.headers["X-Cache"] = "HIT"
            return response

        data = json_ready(loader())
        set_json(app.config, key, data, ttl)
        payload = {"success": True, "data": data} if success_wrapper else data
        response = jsonify(payload)
        response.headers["X-Cache"] = "MISS"
        return response

    def invalidate_cache(*patterns):
        for pattern in patterns:
            delete_pattern(app.config, f"maoning:{pattern}")

    def normalize_feedback_category(value):
        category = clean_text(value)
        return category if category in feedback_categories else "其他问题"

    def analyze_feedback_sentiment_locally(content):
        text = clean_text(content).lower()
        negative_words = (
            "不好", "不能", "无法", "失败", "报错", "错误", "卡", "卡顿", "崩溃", "闪退",
            "慢", "太慢", "麻烦", "难用", "不好用", "没有", "缺少", "不满意", "失望",
            "差", "很差", "糟糕", "问题", "异常", "打不开", "不行", "投诉", "建议改",
            "bug", "error", "fail", "failed", "slow", "crash", "problem",
        )
        positive_words = (
            "好", "很好", "好用", "满意", "喜欢", "方便", "顺畅", "稳定", "清晰",
            "漂亮", "美观", "不错", "可以", "感谢", "支持", "赞", "优秀", "完善",
            "good", "great", "nice", "thanks", "thank", "excellent",
        )
        negative_score = sum(1 for word in negative_words if word in text)
        positive_score = sum(1 for word in positive_words if word in text)
        return "消极" if negative_score > positive_score else "积极"

    def classify_feedback_locally(content):
        text = clean_text(content).lower()
        rules = [
            ("账号登录", ("登录", "微信", "头像", "昵称", "邮箱", "用户", "权限", "管理员", "openid")),
            ("性能卡顿", ("卡顿", "很慢", "太慢", "加载慢", "延迟", "timeout", "slow")),
            ("功能异常", ("报错", "错误", "打不开", "不能", "无法", "失败", "闪退", "崩溃", "bug", "error", "fail")),
            ("数据内容", ("数据", "记录", "列表", "统计", "乱码", "图片", "视频", "金额", "重量", "地址")),
            ("页面体验", ("页面", "样式", "布局", "按钮", "显示", "看不到", "不美观", "字体", "图标")),
            ("反馈建议", ("建议", "希望", "能不能", "可否", "增加", "优化", "改进")),
        ]
        for category, words in rules:
            if any(word in text for word in words):
                return category
        return "其他问题"

    def analyze_feedback_locally(content):
        return {
            "sentiment": analyze_feedback_sentiment_locally(content),
            "problem_category": classify_feedback_locally(content),
        }

    def analyze_feedback_sentiment(content):
        return analyze_feedback(content)["sentiment"]

    def analyze_feedback(content):
        api_key = clean_text(app.config.get("DEEPSEEK_API_KEY"))
        if not api_key:
            return analyze_feedback_locally(content)

        api_base = clean_text(app.config.get("DEEPSEEK_API_BASE")) or "https://api.deepseek.com"
        model = clean_text(app.config.get("DEEPSEEK_MODEL")) or "deepseek-chat"
        url = f"{api_base.rstrip('/')}/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是小程序用户反馈分析器。判断反馈整体情感和问题分类。"
                        "情感只能是：积极、消极。"
                        "问题分类只能是：功能异常、页面体验、性能卡顿、账号登录、数据内容、反馈建议、其他问题。"
                        "只返回 JSON，例如 {\"sentiment\":\"消极\",\"problem_category\":\"功能异常\"}。"
                    ),
                },
                {
                    "role": "user",
                    "content": clean_text(content),
                },
            ],
            "temperature": 0,
            "max_tokens": 80,
            "stream": False,
        }
        req = urllib_request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib_request.urlopen(req, timeout=5) as response:
                result = json.loads(response.read().decode("utf-8"))
            answer = clean_text(result["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError, ValueError, error.URLError):
            return analyze_feedback_locally(content)

        try:
            parsed = json.loads(answer)
        except ValueError:
            parsed = {}
        if not isinstance(parsed, dict):
            parsed = {}
        if "消极" in answer:
            parsed["sentiment"] = "消极"
        elif "积极" in answer:
            parsed["sentiment"] = "积极"
        for category in feedback_categories:
            if category in answer:
                parsed["problem_category"] = category
                break

        local_result = analyze_feedback_locally(content)
        sentiment = clean_text(parsed.get("sentiment"))
        if "消极" in answer:
            sentiment = "消极"
        elif "积极" in answer:
            sentiment = "积极"
        if sentiment not in ["积极", "消极"]:
            sentiment = local_result["sentiment"]

        return {
            "sentiment": sentiment,
            "problem_category": normalize_feedback_category(parsed.get("problem_category") or local_result["problem_category"]),
        }

    def update_feedback_sentiment_async(feedback_id, content):
        def worker():
            analysis = analyze_feedback(content)
            conn = get_connection(app.config)
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE user_feedbacks
                        SET sentiment = %s, problem_category = %s
                        WHERE id = %s
                        """,
                        (analysis["sentiment"], analysis["problem_category"], feedback_id),
                    )
                conn.commit()
            finally:
                conn.close()
            invalidate_cache("feedbacks:*")

        threading.Thread(target=worker, daemon=True).start()

    def current_openid():
        return clean_text(request.headers.get("X-User-Openid"))

    def get_user_by_openid(openid):
        if not openid:
            return None
        key = cache_key("profile", openid)
        cached = get_json(app.config, key)
        if cached is not None:
            return cached
        conn = get_connection(app.config, dict_cursor=True)
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT openid, nickname, email, avatar_key, user_type
                    FROM user_profiles
                    WHERE openid = %s
                    """,
                    (openid,),
                )
                row = cursor.fetchone()
            if row:
                set_json(app.config, key, json_ready(row), app.config["CACHE_DEFAULT_TTL"])
            return row
        finally:
            conn.close()

    def has_admin_user(cursor):
        cursor.execute("SELECT 1 FROM user_profiles WHERE user_type = '管理员' LIMIT 1")
        return cursor.fetchone() is not None

    def require_user():
        openid = current_openid()
        if not openid:
            return None, (jsonify({"success": False, "msg": "未登录"}), 401)
        user = get_user_by_openid(openid)
        if not user:
            return None, (jsonify({"success": False, "msg": "用户不存在"}), 404)
        return user, None

    def require_admin():
        user, error_response = require_user()
        if error_response:
            return None, error_response
        if user["user_type"] != "管理员":
            return None, (jsonify({"success": False, "msg": "无权限"}), 403)
        return user, None

    def can_access_recycle(user, record):
        if not user or not record:
            return False
        if user["user_type"] == "管理员":
            return True
        return clean_text(record.get("user_openid")) == user["openid"]

    def can_access_trial(user, record):
        if not user or not record:
            return False
        if user["user_type"] == "管理员":
            return True
        return clean_text(record.get("user_openid")) == user["openid"]

    def format_profile(row):
        if not row:
            return None
        return {
            "openid": row["openid"],
            "nickname": row["nickname"],
            "email": row["email"],
            "avatar": asset_path("public", row["avatar_key"]) if row.get("avatar_key") else "",
            "userType": row["user_type"],
        }

    def route(rule, **options):
        def decorator(func):
            endpoint = options.pop("endpoint", None)
            app.route(rule, endpoint=endpoint, **options)(func)
            prefixed_endpoint = f"{endpoint or func.__name__}_maoning"
            app.route(f"/maoning{rule}", endpoint=prefixed_endpoint, **options)(func)
            return func
        return decorator

    bucket_map = {
        "maosha": app.config["MINIO_BUCKET_MAOSHA"],
        "maoshashiyong": app.config["MINIO_BUCKET_SHIYONG"],
        "public": app.config["MINIO_BUCKET_PUBLIC"],
    }

    def asset_path(bucket_alias, object_name):
        if not object_name:
            return None
        return f"/api/assets/{bucket_alias}/{object_name}"

    @route("/healthz", methods=["GET"])
    def healthz():
        return jsonify({"success": True})

    @route("/api/auth/wechat-login", methods=["POST"])
    def wechat_login():
        data = request.get_json(silent=True) or {}
        code = clean_text(data.get("code"))

        if not code:
            return jsonify({"success": False, "msg": "缺少登录 code"}), 400
        if not app.config["WECHAT_APP_ID"] or not app.config["WECHAT_APP_SECRET"]:
            return jsonify({"success": False, "msg": "微信登录未配置"}), 500

        query = parse.urlencode(
            {
                "appid": app.config["WECHAT_APP_ID"],
                "secret": app.config["WECHAT_APP_SECRET"],
                "js_code": code,
                "grant_type": "authorization_code",
            }
        )
        url = f"https://api.weixin.qq.com/sns/jscode2session?{query}"

        try:
            with urllib_request.urlopen(url, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except error.URLError:
            return jsonify({"success": False, "msg": "微信服务请求失败"}), 502

        openid = clean_text(payload.get("openid"))
        if not openid:
            return jsonify({"success": False, "msg": payload.get("errmsg") or "微信登录失败"}), 400

        conn = get_connection(app.config)
        try:
            with conn.cursor() as cursor:
                bootstrap_admin = not has_admin_user(cursor)
                cursor.execute(
                    """
                    INSERT INTO user_profiles (openid, user_type)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE openid = VALUES(openid)
                    """,
                    (openid, "管理员" if bootstrap_admin else "普通用户"),
                )
                if bootstrap_admin:
                    cursor.execute(
                        "UPDATE user_profiles SET user_type = '管理员' WHERE openid = %s",
                        (openid,),
                    )
            conn.commit()
        finally:
            conn.close()

        invalidate_cache(f"profile:{parse.quote(openid, safe='')}", "users:*")
        return jsonify({"success": True, "data": format_profile(get_user_by_openid(openid))})

    @route("/api/profile", methods=["GET"])
    def get_profile():
        user, error_response = require_user()
        if error_response:
            return error_response
        return jsonify({"success": True, "data": format_profile(user)})

    @route("/api/profile", methods=["PUT"])
    def update_profile():
        user, error_response = require_user()
        if error_response:
            return error_response

        data = request.get_json(silent=True) or {}
        nickname = clean_text(data.get("nickname")) or user["nickname"] or "微信用户"
        email = clean_text(data.get("email"))
        avatar_key = clean_text(data.get("avatarKey")) or user.get("avatar_key")

        conn = get_connection(app.config)
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE user_profiles
                    SET nickname = %s, email = %s, avatar_key = %s
                    WHERE openid = %s
                    """,
                    (nickname, email, avatar_key or None, user["openid"]),
                )
            conn.commit()
        finally:
            conn.close()

        invalidate_cache(f"profile:{parse.quote(user['openid'], safe='')}", "users:*")
        return jsonify({"success": True, "data": format_profile(get_user_by_openid(user["openid"]))})

    @route("/api/profile/avatar", methods=["POST"])
    def upload_profile_avatar():
        user, error_response = require_user()
        if error_response:
            return error_response

        avatar = request.files.get("avatar")
        if not avatar:
            return jsonify({"success": False, "msg": "缺少头像文件"}), 400

        object_key = upload_image(
            app.config,
            bucket_map["public"],
            avatar,
            object_prefix="profile-avatar",
        )
        return jsonify(
            {
                "success": True,
                "data": {
                    "avatarKey": object_key,
                    "avatar": asset_path("public", object_key),
                },
            }
        )

    @route("/api/feedbacks", methods=["POST"])
    def create_feedback():
        user, error_response = require_user()
        if error_response:
            return error_response

        data = request.get_json(silent=True) or {}
        content = clean_text(data.get("content"))
        if not content:
            return jsonify({"success": False, "msg": "缺少反馈内容"}), 400
        analysis = analyze_feedback_locally(content)
        feedback_id = None

        conn = get_connection(app.config)
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO user_feedbacks
                      (user_openid, nickname_snapshot, email_snapshot, content, sentiment, problem_category)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        user["openid"],
                        user["nickname"],
                        user["email"],
                        content,
                        analysis["sentiment"],
                        analysis["problem_category"],
                    ),
                )
                feedback_id = cursor.lastrowid
            conn.commit()
        finally:
            conn.close()

        invalidate_cache("feedbacks:*")
        if feedback_id:
            update_feedback_sentiment_async(feedback_id, content)

        return jsonify({"success": True, "data": analysis})

    @route("/api/feedbacks", methods=["GET"])
    def list_feedbacks():
        _, error_response = require_admin()
        if error_response:
            return error_response

        def load_feedbacks():
            conn = get_connection(app.config, dict_cursor=True)
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT
                          id, user_openid, nickname_snapshot, email_snapshot, content,
                          sentiment, problem_category, created_at
                        FROM user_feedbacks
                        ORDER BY created_at DESC
                        """
                    )
                    return cursor.fetchall()
            finally:
                conn.close()

        return cached_response(cache_key("feedbacks", "list"), app.config["CACHE_SHORT_TTL"], load_feedbacks)

    @route("/api/feedbacks/stats", methods=["GET"])
    def feedback_stats():
        _, error_response = require_admin()
        if error_response:
            return error_response

        def load_stats():
            conn = get_connection(app.config, dict_cursor=True)
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT
                          SUM(CASE WHEN sentiment = '积极' THEN 1 ELSE 0 END) AS positive,
                          SUM(CASE WHEN sentiment = '消极' THEN 1 ELSE 0 END) AS negative,
                          COUNT(*) AS total
                        FROM user_feedbacks
                        """
                    )
                    row = cursor.fetchone() or {}
                return {
                    "positive": int(row.get("positive") or 0),
                    "negative": int(row.get("negative") or 0),
                    "total": int(row.get("total") or 0),
                }
            finally:
                conn.close()

        return cached_response(cache_key("feedbacks", "stats"), app.config["CACHE_SHORT_TTL"], load_stats)

    @route("/api/feedbacks/negative-top5", methods=["GET"])
    def negative_feedback_top5():
        _, error_response = require_admin()
        if error_response:
            return error_response

        def load_top5():
            conn = get_connection(app.config, dict_cursor=True)
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT problem_category, COUNT(*) AS count
                        FROM user_feedbacks
                        WHERE sentiment = '消极'
                        GROUP BY problem_category
                        ORDER BY count DESC, problem_category ASC
                        LIMIT 5
                        """
                    )
                    return cursor.fetchall()
            finally:
                conn.close()

        return cached_response(cache_key("feedbacks", "negative-top5"), app.config["CACHE_SHORT_TTL"], load_top5)

    @route("/api/users", methods=["GET"])
    def list_users():
        _, error_response = require_admin()
        if error_response:
            return error_response

        def load_users():
            conn = get_connection(app.config, dict_cursor=True)
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT openid, nickname, email, avatar_key, user_type
                        FROM user_profiles
                        ORDER BY updated_at DESC, created_at DESC
                        """
                    )
                    rows = cursor.fetchall()
                return [format_profile(row) for row in rows]
            finally:
                conn.close()

        return cached_response(cache_key("users", "list"), app.config["CACHE_DEFAULT_TTL"], load_users)

    @route("/api/users/<openid>/user-type", methods=["PUT"])
    def update_user_type(openid):
        _, error_response = require_admin()
        if error_response:
            return error_response

        data = request.get_json(silent=True) or {}
        user_type = clean_text(data.get("userType"))
        if user_type not in ["普通用户", "管理员"]:
            return jsonify({"success": False, "msg": "非法用户类型"}), 400

        conn = get_connection(app.config)
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE user_profiles SET user_type = %s WHERE openid = %s",
                    (user_type, openid),
                )
            conn.commit()
        finally:
            conn.close()

        invalidate_cache(f"profile:{parse.quote(openid, safe='')}", "users:*")
        return jsonify({"success": True, "data": format_profile(get_user_by_openid(openid))})

    @route("/api/add_recycle", methods=["POST"])
    def add_recycle():
        user, error_response = require_user()
        if error_response:
            return error_response

        data = request.get_json(silent=True) or {}
        unit = clean_text(data.get("unit"))
        contact = clean_text(data.get("contact"))
        date = clean_text(data.get("date"))
        location = clean_text(data.get("location"))
        weight = data.get("weight")
        herbs = data.get("herbs") or []
        type_ = clean_text(data.get("type", "company")) or "company"

        if type_ not in ["company", "person"]:
            return jsonify({"success": False, "msg": "非法类型"}), 400

        if not all([unit, contact, date, location, weight]):
            return jsonify({"success": False, "msg": "缺少必要字段"}), 400

        herbs_str = ",".join(clean_text(herb) for herb in herbs if clean_text(herb))
        conn = get_connection(app.config)
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO recycle_records(user_openid, unit, contact, date, location, weight, herbs, type)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (user["openid"], unit, contact, date, location, weight, herbs_str, type_),
                )
            conn.commit()
            invalidate_cache("recycles:*", "recycle_detail:*", "recycle_summary:*", "recycle_by_unit:*")
            return jsonify({"success": True})
        except Exception:
            conn.rollback()
            return jsonify({"success": False, "msg": "服务器错误"}), 500
        finally:
            conn.close()

    @route("/api/get_recycles", methods=["GET"])
    def get_recycles():
        user, error_response = require_user()
        if error_response:
            return error_response

        type_filter = request.args.get("type")
        key = cache_key("recycles", user["user_type"], user["openid"], type_filter or "all")

        def load_recycles():
            conn = get_connection(app.config, dict_cursor=True)
            try:
                with conn.cursor() as cursor:
                    sql = """
                        SELECT id, unit AS name, contact, date, location AS address, state AS status, type
                        FROM recycle_records
                    """
                    params = []
                    where_clauses = []
                    if user["user_type"] != "管理员":
                        where_clauses.append("user_openid = %s")
                        params.append(user["openid"])
                    if type_filter in ["company", "person"]:
                        where_clauses.append("type = %s")
                        params.append(type_filter)
                    if where_clauses:
                        sql += " WHERE " + " AND ".join(where_clauses)
                    sql += " ORDER BY created_at DESC"
                    cursor.execute(sql, params)
                    records = cursor.fetchall()

                for record in records:
                    if record["status"] == "pending":
                        record["status"] = "待处理"
                    elif record["status"] == "finish":
                        record["status"] = "已回收"
                return records
            finally:
                conn.close()

        return cached_response(key, app.config["CACHE_DEFAULT_TTL"], load_recycles)

    @route("/api/get_recycle", methods=["GET"])
    def get_recycle():
        user, error_response = require_user()
        if error_response:
            return error_response

        recycle_id = request.args.get("id")
        key = cache_key("recycle_detail", recycle_id, user["openid"], user["user_type"])
        cached = get_json(app.config, key)
        if cached is not None:
            return jsonify({"success": True, "data": cached})

        conn = get_connection(app.config, dict_cursor=True)
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM recycle_records WHERE id = %s", (recycle_id,))
                row = cursor.fetchone()
            if row and can_access_recycle(user, row):
                data = json_ready(row)
                set_json(app.config, key, data, app.config["CACHE_DEFAULT_TTL"])
                return jsonify({"success": True, "data": data})
            if row:
                return jsonify({"success": False, "msg": "无权限"}), 403
            return jsonify({"success": False, "msg": "未找到记录"}), 404
        finally:
            conn.close()

    @route("/api/update_state", methods=["POST"])
    def update_state():
        _, error_response = require_admin()
        if error_response:
            return error_response

        data = request.get_json(silent=True) or {}
        recycle_id = data.get("id")
        new_state = data.get("state")
        approved_weight = data.get("approved_weight")
        batch_no = data.get("batch_no")

        if new_state not in ["pending", "finish"]:
            return jsonify({"success": False, "msg": "非法状态值"}), 400

        conn = get_connection(app.config)
        try:
            with conn.cursor() as cursor:
                if approved_weight is not None and batch_no is not None:
                    cursor.execute(
                        """
                        UPDATE recycle_records
                        SET state = %s, approved_weight = %s, batch_no = %s
                        WHERE id = %s
                        """,
                        (new_state, approved_weight, batch_no, recycle_id),
                    )
                elif approved_weight is not None:
                    cursor.execute(
                        """
                        UPDATE recycle_records
                        SET state = %s, approved_weight = %s
                        WHERE id = %s
                        """,
                        (new_state, approved_weight, recycle_id),
                    )
                elif batch_no is not None:
                    cursor.execute(
                        """
                        UPDATE recycle_records
                        SET state = %s, batch_no = %s
                        WHERE id = %s
                        """,
                        (new_state, batch_no, recycle_id),
                    )
                else:
                    cursor.execute(
                        "UPDATE recycle_records SET state = %s WHERE id = %s",
                        (new_state, recycle_id),
                    )
            conn.commit()
            invalidate_cache("recycles:*", "recycle_detail:*", "recycle_summary:*", "recycle_by_unit:*")
            return jsonify({"success": True})
        except Exception:
            conn.rollback()
            return jsonify({"success": False, "msg": "更新失败"}), 500
        finally:
            conn.close()

    @route("/api/recycle_summary", methods=["GET"])
    def recycle_summary():
        _, error_response = require_admin()
        if error_response:
            return error_response

        type_filter = request.args.get("type")
        key = cache_key("recycle_summary", type_filter or "all")

        def load_summary():
            conn = get_connection(app.config, dict_cursor=True)
            try:
                with conn.cursor() as cursor:
                    sql = """
                        SELECT
                            unit AS name,
                            location AS address,
                            SUM(COALESCE(approved_weight, weight)) AS total_weight,
                            type
                        FROM recycle_records
                        WHERE state = 'finish'
                    """
                    params = []
                    if type_filter in ["company", "person"]:
                        sql += " AND type = %s"
                        params.append(type_filter)
                    sql += " GROUP BY unit, location, type ORDER BY unit ASC, location ASC"
                    cursor.execute(sql, params)
                    rows = cursor.fetchall()
                return [
                    {
                        **json_ready(row),
                        "entity_key": f"{row['name']}::{row['address']}",
                    }
                    for row in rows
                ]
            finally:
                conn.close()

        return cached_response(key, app.config["CACHE_LONG_TTL"], load_summary)

    @route("/api/recycle_by_unit", methods=["GET"])
    def recycle_by_unit():
        _, error_response = require_admin()
        if error_response:
            return error_response

        unit = clean_text(request.args.get("unit"))
        location = clean_text(request.args.get("location"))

        if not unit or not location:
            return jsonify({"success": False, "msg": "缺少名称或地址"}), 400

        key = cache_key("recycle_by_unit", unit, location)

        def load_by_unit():
            conn = get_connection(app.config, dict_cursor=True)
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT DATE(date) AS date, SUM(COALESCE(approved_weight, weight)) AS total_weight
                        FROM recycle_records
                        WHERE state = 'finish' AND unit = %s AND location = %s
                        GROUP BY DATE(date)
                        ORDER BY date ASC
                        """,
                        (unit, location),
                    )
                    records = cursor.fetchall()

                    cursor.execute(
                        """
                        SELECT unit AS name, location, SUM(COALESCE(approved_weight, weight)) AS total
                        FROM recycle_records
                        WHERE state = 'finish' AND unit = %s AND location = %s
                        GROUP BY unit, location
                        """,
                        (unit, location),
                    )
                    meta = cursor.fetchone() or {"name": unit, "location": location, "total": 0}

                return {
                    "records": json_ready(records),
                    "name": meta["name"],
                    "location": meta["location"],
                    "total": json_ready(meta["total"]),
                    "entity_key": f"{meta['name']}::{meta['location']}",
                }
            finally:
                conn.close()

        return cached_response(key, app.config["CACHE_LONG_TTL"], load_by_unit)

    @route("/api/maoning_maosha/products", methods=["GET"])
    def list_maosha_products():
        def load_products():
            conn = get_connection(app.config, dict_cursor=True)
            try:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT * FROM products ORDER BY id DESC")
                    rows = cursor.fetchall()

                data = []
                for row in rows:
                    data.append(
                        {
                            "id": row["id"],
                            "spec": row["spec"],
                            "price": row["price"],
                            "location": row["location"],
                            "phone": row["phone"],
                            "image": asset_path("maosha", row["image_key"]),
                            "erweiimage": asset_path("maosha", row["erweiimage_key"]),
                            "ywymimage": asset_path("maosha", row["ywymimage_key"]),
                        }
                    )
                return data
            finally:
                conn.close()

        return cached_response(cache_key("maosha_products"), app.config["CACHE_LONG_TTL"], load_products, success_wrapper=False)

    @route("/api/maoning_maosha/upload", methods=["POST"])
    def upload_maosha():
        upload_id = request.form.get("uploadId")
        image = request.files.get("image")
        erweiimage = request.files.get("erweiimage")
        ywymimage = request.files.get("ywymimage")

        spec = request.form.get("spec")
        price = request.form.get("price")
        location = request.form.get("location")
        phone = request.form.get("phone")

        if not upload_id and not all([image, spec, price, location, phone]):
            return jsonify({"msg": "missing required fields"}), 400

        conn = get_connection(app.config)
        try:
            created = False
            with conn.cursor() as cursor:
                if not upload_id:
                    image_key = upload_image(app.config, bucket_map["maosha"], image)
                    cursor.execute(
                        """
                        INSERT INTO products (image_key, spec, price, location, phone)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (image_key, spec, price, location, phone),
                    )
                    conn.commit()
                    upload_id = cursor.lastrowid
                    created = True

                if image and not created:
                    cursor.execute(
                        "UPDATE products SET image_key = %s WHERE id = %s",
                        (upload_image(app.config, bucket_map["maosha"], image), upload_id),
                    )
                if erweiimage:
                    cursor.execute(
                        "UPDATE products SET erweiimage_key = %s WHERE id = %s",
                        (upload_image(app.config, bucket_map["maosha"], erweiimage), upload_id),
                    )
                if ywymimage:
                    cursor.execute(
                        "UPDATE products SET ywymimage_key = %s WHERE id = %s",
                        (upload_image(app.config, bucket_map["maosha"], ywymimage), upload_id),
                    )
            conn.commit()
            invalidate_cache("maosha_products")
            return jsonify({"msg": "success", "uploadId": upload_id})
        except Exception:
            conn.rollback()
            return jsonify({"msg": "upload failed"}), 500
        finally:
            conn.close()

    @route("/api/maoning_maoshashiyong/products", methods=["GET"])
    def list_maoshashiyong_products():
        user, error_response = require_user()
        if error_response:
            return error_response

        key = cache_key("maoshashiyong_products", user["user_type"], user["openid"])

        def load_trial_products():
            conn = get_connection(app.config, dict_cursor=True)
            try:
                with conn.cursor() as cursor:
                    if user["user_type"] == "管理员":
                        cursor.execute("SELECT * FROM maosha_shiyong ORDER BY id DESC")
                    else:
                        cursor.execute(
                            "SELECT * FROM maosha_shiyong WHERE user_openid = %s ORDER BY id DESC",
                            (user["openid"],),
                        )
                    rows = cursor.fetchall()
                return [
                    {
                        "id": row["id"],
                        "image": asset_path("maoshashiyong", row["image_key"]),
                        "name": row["name"],
                        "phone": row["phone"],
                        "status": row["status"],
                    }
                    for row in rows
                ]
            finally:
                conn.close()

        return cached_response(key, app.config["CACHE_DEFAULT_TTL"], load_trial_products, success_wrapper=False)

    @route("/api/maoning_maoshashiyong/upload", methods=["POST"])
    def upload_maoshashiyong():
        user, error_response = require_user()
        if error_response:
            return error_response

        image = request.files.get("image")
        name = request.form.get("name")
        phone = request.form.get("phone")

        if not all([image, name, phone]):
            return jsonify({"msg": "missing required fields"}), 400

        conn = get_connection(app.config)
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO maosha_shiyong (user_openid, image_key, name, phone)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (user["openid"], upload_image(app.config, bucket_map["maoshashiyong"], image), name, phone),
                )
            conn.commit()
            invalidate_cache("maoshashiyong_products:*")
            return jsonify({"msg": "success"})
        except Exception:
            conn.rollback()
            return jsonify({"msg": "upload failed"}), 500
        finally:
            conn.close()

    @route("/api/maoning_maoshashiyong/product", methods=["GET"])
    def get_maoshashiyong_product():
        user, error_response = require_user()
        if error_response:
            return error_response

        product_id = request.args.get("id")
        key = cache_key("maoshashiyong_product", product_id, user["openid"], user["user_type"])
        cached = get_json(app.config, key)
        if cached is not None:
            return jsonify(cached)

        conn = get_connection(app.config, dict_cursor=True)
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM maosha_shiyong WHERE id = %s", (product_id,))
                row = cursor.fetchone()
            if not row:
                return jsonify({"success": False, "msg": "未找到记录"}), 404
            if not can_access_trial(user, row):
                return jsonify({"success": False, "msg": "无权限"}), 403
            data = {
                "id": row["id"],
                "image": asset_path("maoshashiyong", row["image_key"]),
                "name": row["name"],
                "phone": row["phone"],
                "status": row["status"],
            }
            set_json(app.config, key, data, app.config["CACHE_DEFAULT_TTL"])
            return jsonify(data)
        finally:
            conn.close()

    @route("/api/maoning_maoshashiyong/update", methods=["POST"])
    def update_maoshashiyong():
        _, error_response = require_admin()
        if error_response:
            return error_response

        data = request.get_json(silent=True) or {}
        product_id = data.get("id")
        state = data.get("state")

        if state not in ["pending", "approve"]:
            return jsonify({"success": False, "msg": "非法状态值"}), 400

        conn = get_connection(app.config)
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE maosha_shiyong SET status = %s WHERE id = %s",
                    (state, product_id),
                )
                affected = cursor.rowcount
            conn.commit()
            if affected > 0:
                invalidate_cache("maoshashiyong_products:*", "maoshashiyong_product:*")
                return jsonify({"success": True, "msg": "更新成功"})
            return jsonify({"success": False, "msg": "更新失败或未找到记录"}), 404
        except Exception:
            conn.rollback()
            return jsonify({"success": False, "msg": "更新失败"}), 500
        finally:
            conn.close()

    @route("/api/assets/<bucket_alias>/<path:object_name>", methods=["GET"])
    def get_asset(bucket_alias, object_name):
        bucket = bucket_map.get(bucket_alias)
        if not bucket:
            return jsonify({"success": False, "msg": "bucket not found"}), 404

        try:
            file_obj, content_type = fetch_object(app.config, bucket, object_name)
            return send_file(file_obj, mimetype=content_type, download_name=object_name)
        except Exception:
            return jsonify({"success": False, "msg": "asset not found"}), 404
