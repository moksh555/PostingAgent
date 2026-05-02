from app.api.depends.repositoryDepends import get_s3_connection
import asyncio
from configurations.config import config
async def get_file_content(bucket_name, object_name):
    s3 = get_s3_connection()
    response = await s3.get_file(bucketName=bucket_name, key=object_name)
    body = await response["Body"].read()
    return body.decode("utf-8")

if __name__ == "__main__":
    key = "UserNotes/test_user_moksh/knowledge/previous_summary.txt"
    text = asyncio.run(get_file_content(config.AWS_BUCKET_NAME, key))
    print(f"{key!r} -> length {len(text)!r}")
    print(repr(text[:2000]) if len(text) > 2000 else repr(text))