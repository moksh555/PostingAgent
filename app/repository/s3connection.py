import aioboto3  # type: ignore
from configurations.config import config
from app.errorsHandler.errors import (
    FailedToPutObjectToS3, 
    FailedToGetFileFromS3,
    FailedToWriteSummaryToS3
    )
from app.models.AgentModels import AgentSummary

class S3Connection:
    def __init__(self):
        self.session = aioboto3.Session(
            aws_access_key_id=config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
            region_name=config.AWS_DEFAULT_REGION,
        )

    async def put_object(self, body, bucketName, key):
        try:
            async with self.session.client("s3") as client:
                return await client.put_object(
                Body=body, 
                Bucket=bucketName, 
                Key=key
                )
        except Exception as e:
            raise FailedToPutObjectToS3(f"Failed to put object to S3: {e}") from e

    async def get_file(self, bucketName, key):
        try:
            async with self.session.client("s3") as client:
                return await client.get_object(
                    Bucket=bucketName, 
                    Key=key
                    )
        except Exception as e:
            raise FailedToGetFileFromS3(f"Failed to get object from S3: {e}") from e
    
    async def check_if_file_exists(self, bucketName, key):
        try:
            async with self.session.client("s3") as client:
                await client.head_object(
                    Bucket=bucketName,
                    Key=key
                )
                return True
        except Exception as e:
            return False
    
    # Write Summary to S3: This function will write the marekting summary to the S3 bucket and return the URL(This is not the node in graph but it is a helper function)
    async def writeSummaryToS3(self, notes: AgentSummary, userId: str) -> str:
        try:
            await self.put_object(
                body=notes.marketingBrief,
                bucketName=config.AWS_BUCKET_NAME,
                key=f"UserNotes/{userId}/{notes.fileName}",
            )
            return f"https://{config.AWS_BUCKET_NAME}.s3.{config.AWS_DEFAULT_REGION}.amazonaws.com/UserNotes/{userId}/{notes.fileName}"
        except Exception as e:
            raise FailedToWriteSummaryToS3(f"Failed to write summary to S3 with connection error: {e}") from e


       