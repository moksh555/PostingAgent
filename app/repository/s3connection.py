import boto3  # type: ignore
from configurations.config import config
from pathlib import Path


class S3Connection:
    def __init__(self):
        self.client = boto3.client(
            "s3",
            aws_access_key_id=config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
            region_name=config.AWS_DEFAULT_REGION,
        )

    def get_client(self):
        return self.client

    def get_bucket(self):
        return self.client.Bucket(config.AWS_BUCKET_NAME)

    def put_object(self, body, bucketName, key):
        return self.client.put_object(Body=body, Bucket=bucketName, Key=key)

    def get_file(self, bucketName, key):
        return self.client.get_object(Bucket=bucketName, Key=key)
