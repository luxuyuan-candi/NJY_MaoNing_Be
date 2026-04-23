import io
import uuid

import boto3
from botocore.exceptions import ClientError


def create_s3_client(config):
    return boto3.client(
        "s3",
        endpoint_url=config["MINIO_ENDPOINT"],
        aws_access_key_id=config["MINIO_ACCESS_KEY"],
        aws_secret_access_key=config["MINIO_SECRET_KEY"],
    )


def ensure_buckets(config):
    client = create_s3_client(config)
    for bucket in [config["MINIO_BUCKET_MAOSHA"], config["MINIO_BUCKET_SHIYONG"]]:
        try:
            client.head_bucket(Bucket=bucket)
        except ClientError:
            client.create_bucket(Bucket=bucket)
        except Exception:
            # Allow the API to start before MinIO is ready; upload paths will retry lazily.
            return


def ensure_bucket_exists(config, bucket):
    client = create_s3_client(config)
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        client.create_bucket(Bucket=bucket)


def upload_image(config, bucket, file_storage):
    ensure_bucket_exists(config, bucket)
    extension = file_storage.filename.rsplit(".", 1)[-1].lower() if "." in file_storage.filename else "jpg"
    object_name = f"{uuid.uuid4()}.{extension}"
    file_storage.stream.seek(0)
    create_s3_client(config).upload_fileobj(
        file_storage.stream,
        bucket,
        object_name,
        ExtraArgs={"ContentType": file_storage.mimetype or "application/octet-stream"},
    )
    return object_name


def fetch_object(config, bucket, object_name):
    ensure_bucket_exists(config, bucket)
    response = create_s3_client(config).get_object(Bucket=bucket, Key=object_name)
    body = response["Body"].read()
    return io.BytesIO(body), response.get("ContentType", "application/octet-stream")
