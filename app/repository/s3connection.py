import boto3  # type: ignore
from configurations.config import config
from app.errorsHandler.errors import (
    FailedToPutObjectToS3, 
    FailedToGetFileFromS3
    )

class S3Connection:
    def __init__(self):
        self.client = boto3.client(
            "s3",
            aws_access_key_id=config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
            region_name=config.AWS_DEFAULT_REGION,
        )

    async def get_client(self):
        return self.client

    async def get_bucket(self):
        return self.client.Bucket(
            config.AWS_BUCKET_NAME
            )

    async def put_object(self, body, bucketName, key):
        try:
            return self.client.put_object(
                Body=body, 
                Bucket=bucketName, 
                Key=key
                )
        except Exception as e:
            raise FailedToPutObjectToS3(f"Failed to put object to S3: {e}") from e

    async def get_file(self, bucketName, key):
        try:
            return self.client.get_object(
            Bucket=bucketName, 
                Key=key
                )
        except Exception as e:
            raise FailedToGetFileFromS3(f"Failed to get object from S3: {e}") from e
