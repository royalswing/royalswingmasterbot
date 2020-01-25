import os

import boto3
dynamodb = boto3.resource('dynamodb')


def delete(event: dict, context) -> dict:
    table = dynamodb.Table(os.environ['ACHIEVEMENTS_TABLE'])

    table.delete_item(
        Key={
            'user_id': event['pathParameters']['id']
        }
    )

    response = {
        'statusCode': 204
    }
    return response
