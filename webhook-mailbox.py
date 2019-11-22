#!/usr/bin/env python3
import io
import json
import random
import shlex
import textwrap
import time
import zipfile

import boto3
import botocore.exceptions
import click


# Functions for naming our AWS resources
def create_queue_name():
    return 'webhook-mailbox-' + ''.join(random.choices('0123456789abcdef', k=6))

def get_api_name(queue_name):
    return queue_name

def get_consumer_name(queue_name):
    return f'{queue_name}-consumer'

def get_function_name(queue_name):
    return queue_name

def get_producer_role_name(queue_name):
    return f'{queue_name}-producer'


# Generates the code
def get_lambda_code(queue_name):
    return textwrap.dedent(f'''\
    import boto3
    import json

    sqs = boto3.resource('sqs')
    queue = sqs.get_queue_by_name(QueueName='{queue_name}')

    def lambda_handler(event, context):
        queue.send_message(MessageBody=json.dumps(event))
        response = {{
            'body': json.dumps({{ 'result': 'ok' }}),
            'headers': {{ 'Content-Type': 'application/json' }},
            'statusCode': '200',
        }}
        return response
    ''')


# Lambda wants us to provide our code as a Zip archive. We can construct it in-
# memory, but we need to explicitly set the file's executable bit.
def zip_code(module_name, code):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as z:
        info = zipfile.ZipInfo(f'{module_name}.py')
        info.external_attr = 0o100755 << 16
        z.writestr(info, code)
    return buffer.getvalue()


@click.group()
def cli():
    pass


@cli.command()
def configure():
    queue_name = create_queue_name()
    api_name = get_api_name(queue_name)
    consumer_name = get_consumer_name(queue_name)
    function_name = get_function_name(queue_name)
    producer_role_name = get_producer_role_name(queue_name)

    # Create the queue
    sqs = boto3.client('sqs')
    response = sqs.create_queue(QueueName=queue_name)
    queue_url = response['QueueUrl']

    # Get the queue's resource ARN
    response = sqs.get_queue_attributes(
        QueueUrl=queue_url,
        AttributeNames=[ 'QueueArn', ]
    )
    queue_arn = response['Attributes']['QueueArn']

    # Create a user who will be able to consume this queue
    iam = boto3.client('iam')
    iam.create_user(UserName=consumer_name)

    # Attach a policy to this user to grant it read access
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "QueueConsumer",
                "Effect": "Allow",
                "Action": [
                    "sqs:DeleteMessage",
                    "sqs:GetQueueAttributes",
                    "sqs:GetQueueUrl",
                    "sqs:PurgeQueue",
                    "sqs:ReceiveMessage",
                ],
                "Resource": queue_arn,
            },
        ],
    }
    iam.put_user_policy(
        UserName=consumer_name,
        PolicyName=consumer_name,
        PolicyDocument=json.dumps(policy)
    )

    # Create an access key for the consumer user
    response = iam.create_access_key(UserName=consumer_name)
    access_key_id = response['AccessKey']['AccessKeyId']
    secret_access_key = response['AccessKey']['SecretAccessKey']

    # Create a producer role that can be assumed by Lambda
    assume_role_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": "lambda.amazonaws.com"
                },
                "Action": "sts:AssumeRole"
            },
        ],
    }
    response = iam.create_role(
        RoleName=producer_role_name,
        AssumeRolePolicyDocument=json.dumps(assume_role_policy)
    )
    producer_role_arn = response['Role']['Arn']

    # Attach a policy to this role to grant it write access
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "QueueProducer",
                "Effect": "Allow",
                "Action": [
                    "sqs:GetQueueUrl",
                    "sqs:SendMessage",
                    "sqs:GetQueueAttributes"
                ],
                "Resource": queue_arn,
            }
        ]
    }
    iam.put_role_policy(
        RoleName=producer_role_name,
        PolicyName=producer_role_name,
        PolicyDocument=json.dumps(policy)
    )

    # Create a Lambda function. We need to retry a few times until our IAM role
    # is visible to Lambda.
    lam = boto3.client('lambda')
    for i in range(14):
        try:
            response = lam.create_function(
                FunctionName=function_name,
                Runtime='python3.7',
                Role=producer_role_arn,
                Handler='main.lambda_handler',
                Code={
                    'ZipFile': zip_code('main', get_lambda_code(queue_name))
                }
            )
            function_arn = response['FunctionArn']
            break
        except botocore.exceptions.ClientError as e:
            if 'cannot be assumed' in e.response['Error']['Message']:
                time.sleep(i)  # linear back-off, ~1.5 minutes total
                continue
            raise
    else:
        raise Exception('Timed out trying to create Lambda function')

    
    # Create an API Gateway REST API
    gway = boto3.client('apigateway')
    response = gway.create_rest_api(name=api_name)
    api_id = response['id']

    # Find the root resource
    response = gway.get_resources(restApiId=api_id)
    assert response['items'][0]['path'] == '/'
    root_id = response['items'][0]['id']

    # Create a catch-all resource under the root
    response = gway.create_resource(
        restApiId=api_id,
        parentId=root_id,
        pathPart='{proxy+}'
    )
    catch_all_id = response['id']

    # Define an ANY method on the root and catch-all resources
    for resource_id in [root_id, catch_all_id]:
        gway.put_method(
            restApiId=api_id,
            resourceId=resource_id,
            httpMethod='ANY',
            authorizationType='NONE'
        )

    # Construct the URI for the Lambda function we will invoke
    sections = function_arn.split(':')
    region, account_id = sections[3], sections[4]
    function_uri = f'arn:aws:apigateway:{region}:lambda:path/2015-03-31/' \
                   f'functions/{function_arn}/invocations'

    # Create an integration so that incoming requests are forward to the Lambda
    for resource_id in [root_id, catch_all_id]:
        gway.put_integration(
            restApiId=api_id,
            resourceId=resource_id,
            httpMethod='ANY',
            type='AWS_PROXY',
            integrationHttpMethod='POST',
            uri=function_uri
        )

    # Allow the integration to invoke the Lambda function
    lam.add_permission(
        FunctionName=function_name,
        StatementId=f'RestApiInvoke',
        Action='lambda:InvokeFunction',
        Principal='apigateway.amazonaws.com',
        SourceArn=f'arn:aws:execute-api:{region}:{account_id}:{api_id}/*'
    )

    # Create a deployment for the REST API to make it publicly accessible
    gway.create_deployment(restApiId=api_id, stageName='prod')

    # Finished
    print('Configured queue', queue_name, 'with the following credentials:')
    print(f'  AWS_ACCESS_KEY_ID={shlex.quote(access_key_id)}')
    print(f'  AWS_SECRET_ACCESS_KEY={shlex.quote(secret_access_key)}')
    print()
    print('URL:', f'https://{api_id}.execute-api.{region}.amazonaws.com/prod/')


@cli.command()
@click.argument('queue_name')
def unconfigure(queue_name):
    api_name = get_api_name(queue_name)
    consumer_name = get_consumer_name(queue_name)
    function_name = get_function_name(queue_name)
    producer_role_name = get_producer_role_name(queue_name)

    # Delete the queue itself
    sqs = boto3.client('sqs')
    response = sqs.get_queue_url(QueueName=queue_name)
    sqs.delete_queue(QueueUrl=response['QueueUrl'])

    # Delete the Lambda function
    lam = boto3.client('lambda')
    lam.delete_function(FunctionName=function_name)

    # Delete the REST API
    gway = boto3.client('apigateway')
    response = gway.get_rest_apis()
    for api in response['items']:
        if api['name'] == api_name:
            gway.delete_rest_api(restApiId=api['id'])
            break
    else:
        raise ValueError(f'REST API {api_name} not found')

    # Delete the consumer user
    iam = boto3.client('iam')
    response = iam.list_access_keys(UserName=consumer_name)
    for access_key in response['AccessKeyMetadata']:
        iam.delete_access_key(
            UserName=consumer_name,
            AccessKeyId=access_key['AccessKeyId']
        )
    
    iam.delete_user_policy(UserName=consumer_name, PolicyName=consumer_name)
    iam.delete_user(UserName=consumer_name)

    # Delete the producer role
    iam.delete_role_policy(
        RoleName=producer_role_name,
        PolicyName=producer_role_name
    )
    iam.delete_role(RoleName=producer_role_name)

    print('Deleted queue', queue_name)


if __name__ == '__main__':
    cli()
