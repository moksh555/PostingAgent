import boto3 #type: ignore
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
        return self.client.put_object(
            Body=body, 
            Bucket=bucketName, 
            Key=key
            )
    
    def get_file(self, bucketName, key):
        return self.client.get_object(
            Bucket=bucketName, 
            Key=key
            )



if __name__ == "__main__":
    s3 = S3Connection()
    
    try:
        response = s3.put_object(
            body="test moksh",
            bucketName=config.AWS_BUCKET_NAME,
            key="images/test.txt",
        ) 
        print(response)

        print("--------------------------------")
        response = s3.get_file(
            bucketName=config.AWS_BUCKET_NAME,
            key="images/tt.txt",
        )
        content = response['Body'].read().decode('utf-8')
        print(content)
        print("--------------------------------")
    except Exception as e:
        print(e)