import boto3
from botocore.exceptions import ClientError

sts = boto3.client('sts', region_name='us-east-1')

try:
    response = sts.assume_root(
        TargetPrincipal='YOUR_MEMBER_ACCOUNT_ID',  # e.g. '123456789012'
        TaskPolicyArn={'arn': 'arn:aws:iam::aws:policy/root-task/IAMDeleteRootUserCredentials'},
        DurationSeconds=900
    )
    print("Success! Got temporary credentials (do NOT print full response in prod).")
    print("AccessKeyId:", response['Credentials']['AccessKeyId'])  # Just to confirm — never log secret/token
except ClientError as e:
    print("Error:", e.response['Error'])