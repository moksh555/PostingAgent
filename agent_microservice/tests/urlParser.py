if __name__ == "__main__":
    import boto3
    from configurations.config import config
    import os
    from urllib.parse import urlparse

    parsed = urlparse("https://posting-agent-bucket.s3.us-east-2.amazonaws.com/UserNotes/test_user/claude_agent_sdk_brief.txt")
    
    # Extract bucket and key
    bucket = parsed.netloc.split('.s3.')[0]        # posting-agent-bucket
    key = parsed.path.lstrip('/')                   # UserNotes/test_user/claude_agent_sdk_brief.txt

    print(f"Bucket: {bucket}")
    print(f"Key: {key}")

    # Use boto3 to get the object
    s3_client = boto3.client(
        's3',
        region_name='us-east-1',
        aws_access_key_id=config.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY
    )

    response = s3_client.get_object(Bucket=bucket, Key=key)
    content = response['Body'].read().decode('utf-8')
    print(content)