from langchain.tools import tool, ToolRuntime #type: ignore
from app.repository.s3connection import get_s3_connection
from configurations.config import config

@tool
async def get_file_content_S3(key: str) -> str:
    """
    Get the content of a file from the S3 bucket for a specific user.

    The S3 bucket is organized as follows:
        UserNotes/{userId}/
            ├── knowledge/
            │   ├── previous_summary.txt     → summary of previous campaign notes
            │   └── feedback_summary.txt     → summary of human feedback on past posts
            └── {fileName}.txt               → marketing brief for a specific campaign

    Args:
        key: The full S3 key path to the file. Must be one of:
            - "UserNotes/{userId}/knowledge/previous_summary.txt" for previous campaign summary
            - "UserNotes/{userId}/knowledge/feedback_summary.txt" for human feedback summary
            - "UserNotes/{userId}/{fileName}.txt" for a specific marketing brief

    Returns:
        The text content of the file as a string.
    """
    file = await get_s3_connection().get_file(config.AWS_BUCKET_NAME, key)
    return await file["Body"].read().decode("utf-8")

@tool
async def check_if_file_exists_S3(key: str) -> bool:
    """
    Check if a file exists in the S3 bucket for a specific user.

    The S3 bucket is organized as follows:
        UserNotes/{userId}/
            ├── knowledge/
            │   ├── previous_summary.txt     → summary of previous campaign notes
            │   └── feedback_summary.txt     → summary of human feedback on past posts
            └── {fileName}.txt               → marketing brief for a specific campaign

    Args:
        key: The full S3 key path to the file. Must be one of:
            - "UserNotes/{userId}/knowledge/previous_summary.txt" for previous campaign summary
            - "UserNotes/{userId}/knowledge/feedback_summary.txt" for human feedback summary
            - "UserNotes/{userId}/{fileName}.txt" for a specific marketing brief
    """
    return await get_s3_connection().check_if_file_exists(config.AWS_BUCKET_NAME, key)

@tool
async def write_file_to_S3(body: str, key: str) -> bool:
    """
    Write a file to the S3 bucket for a specific user.

    The S3 bucket is organized as follows:
        UserNotes/{userId}/
            ├── knowledge/
            │   ├── previous_summary.txt     → summary of previous campaign notes
            │   └── feedback_summary.txt     → summary of human feedback on past posts
            └── {fileName}.txt               → marketing brief for a specific campaign

    Args:
        key: The full S3 key path to the file.
        body: The body of the file to write.
    """
    return await get_s3_connection().put_object(body=body, bucketName=config.AWS_BUCKET_NAME, key=key)