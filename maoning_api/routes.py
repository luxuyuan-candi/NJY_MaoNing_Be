from flask import jsonify, request, send_file

from .db import get_connection, json_ready
from .storage import fetch_object, upload_image


def register_routes(app):
    bucket_map = {
        "maosha": app.config["MINIO_BUCKET_MAOSHA"],
        "maoshashiyong": app.config["MINIO_BUCKET_SHIYONG"],
    }

    def asset_path(bucket_alias, object_name):
        if not object_name:
            return None
        return f"/api/assets/{bucket_alias}/{object_name}"

    @app.get("/healthz")
    def healthz():
        return jsonify({"success": True})

    @app.post("/api/add_recycle")
    def add_recycle():
        data = request.get_json(silent=True) or {}
        unit = data.get("unit")
        contact = data.get("contact")
        date = data.get("date")
        location = data.get("location")
        weight = data.get("weight")
        herbs = data.get("herbs") or []
        type_ = data.get("type", "company")

        if not all([unit, contact, date, location, weight]):
            return jsonify({"success": False, "msg": "缺少必要字段"}), 400

        herbs_str = ",".join(herbs)
        conn = get_connection(app.config)
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO recycle_records(unit, contact, date, location, weight, herbs, type)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (unit, contact, date, location, weight, herbs_str, type_),
                )
            conn.commit()
            return jsonify({"success": True})
        except Exception:
            conn.rollback()
            return jsonify({"success": False, "msg": "服务器错误"}), 500
        finally:
            conn.close()

    @app.get("/api/get_recycles")
    def get_recycles():
        type_filter = request.args.get("type")
        conn = get_connection(app.config, dict_cursor=True)
        try:
            with conn.cursor() as cursor:
                sql = """
                    SELECT id, unit AS name, contact, date, location AS address, state AS status, type
                    FROM recycle_records
                """
                params = []
                if type_filter in ["company", "person"]:
                    sql += " WHERE type = %s"
                    params.append(type_filter)
                sql += " ORDER BY created_at DESC"
                cursor.execute(sql, params)
                records = cursor.fetchall()

            for record in records:
                if record["status"] == "pending":
                    record["status"] = "待处理"
                elif record["status"] == "finish":
                    record["status"] = "已回收"

            return jsonify({"success": True, "data": json_ready(records)})
        finally:
            conn.close()

    @app.get("/api/get_recycle")
    def get_recycle():
        recycle_id = request.args.get("id")
        conn = get_connection(app.config, dict_cursor=True)
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM recycle_records WHERE id = %s", (recycle_id,))
                row = cursor.fetchone()
            if row:
                return jsonify({"success": True, "data": json_ready(row)})
            return jsonify({"success": False, "msg": "未找到记录"}), 404
        finally:
            conn.close()

    @app.post("/api/update_state")
    def update_state():
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
            return jsonify({"success": True})
        except Exception:
            conn.rollback()
            return jsonify({"success": False, "msg": "更新失败"}), 500
        finally:
            conn.close()

    @app.get("/api/recycle_summary")
    def recycle_summary():
        type_filter = request.args.get("type")
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
                sql += " GROUP BY unit, location, type"
                cursor.execute(sql, params)
                rows = cursor.fetchall()
            return jsonify({"success": True, "data": json_ready(rows)})
        finally:
            conn.close()

    @app.get("/api/recycle_by_unit")
    def recycle_by_unit():
        unit = request.args.get("unit")
        location = request.args.get("location")
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
                    SELECT location, SUM(COALESCE(approved_weight, weight)) AS total
                    FROM recycle_records
                    WHERE state = 'finish' AND unit = %s AND location = %s
                    GROUP BY location
                    """,
                    (unit, location),
                )
                meta = cursor.fetchone() or {"location": location, "total": 0}

            return jsonify(
                {
                    "success": True,
                    "data": {
                        "records": json_ready(records),
                        "location": meta["location"],
                        "total": json_ready(meta["total"]),
                    },
                }
            )
        finally:
            conn.close()

    @app.get("/api/maoning_maosha/products")
    def list_maosha_products():
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
            return jsonify(data)
        finally:
            conn.close()

    @app.post("/api/maoning_maosha/upload")
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
            return jsonify({"msg": "success", "uploadId": upload_id})
        except Exception:
            conn.rollback()
            return jsonify({"msg": "upload failed"}), 500
        finally:
            conn.close()

    @app.get("/api/maoning_maoshashiyong/products")
    def list_maoshashiyong_products():
        conn = get_connection(app.config, dict_cursor=True)
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM maosha_shiyong ORDER BY id DESC")
                rows = cursor.fetchall()
            return jsonify(
                [
                    {
                        "id": row["id"],
                        "image": asset_path("maoshashiyong", row["image_key"]),
                        "name": row["name"],
                        "phone": row["phone"],
                        "status": row["status"],
                    }
                    for row in rows
                ]
            )
        finally:
            conn.close()

    @app.post("/api/maoning_maoshashiyong/upload")
    def upload_maoshashiyong():
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
                    INSERT INTO maosha_shiyong (image_key, name, phone)
                    VALUES (%s, %s, %s)
                    """,
                    (upload_image(app.config, bucket_map["maoshashiyong"], image), name, phone),
                )
            conn.commit()
            return jsonify({"msg": "success"})
        except Exception:
            conn.rollback()
            return jsonify({"msg": "upload failed"}), 500
        finally:
            conn.close()

    @app.get("/api/maoning_maoshashiyong/product")
    def get_maoshashiyong_product():
        product_id = request.args.get("id")
        conn = get_connection(app.config, dict_cursor=True)
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM maosha_shiyong WHERE id = %s", (product_id,))
                row = cursor.fetchone()
            if not row:
                return jsonify({"success": False, "msg": "未找到记录"}), 404
            return jsonify(
                {
                    "id": row["id"],
                    "image": asset_path("maoshashiyong", row["image_key"]),
                    "name": row["name"],
                    "phone": row["phone"],
                    "status": row["status"],
                }
            )
        finally:
            conn.close()

    @app.post("/api/maoning_maoshashiyong/update")
    def update_maoshashiyong():
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
                return jsonify({"success": True, "msg": "更新成功"})
            return jsonify({"success": False, "msg": "更新失败或未找到记录"}), 404
        except Exception:
            conn.rollback()
            return jsonify({"success": False, "msg": "更新失败"}), 500
        finally:
            conn.close()

    @app.get("/api/assets/<bucket_alias>/<path:object_name>")
    def get_asset(bucket_alias, object_name):
        bucket = bucket_map.get(bucket_alias)
        if not bucket:
            return jsonify({"success": False, "msg": "bucket not found"}), 404

        try:
            file_obj, content_type = fetch_object(app.config, bucket, object_name)
            return send_file(file_obj, mimetype=content_type, download_name=object_name)
        except Exception:
            return jsonify({"success": False, "msg": "asset not found"}), 404
