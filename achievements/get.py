import json
import os
from achievements import decimalencoder
import boto3
dynamodb = boto3.resource('dynamodb')


def get(event: dict, context) -> dict:
    table = dynamodb.Table(os.environ['ACHIEVEMENTS_TABLE'])

    # получим все достижения текущего пользователя
    result = table.get_item(
        Key={
            'user_id': int(event['pathParameters']['id'])
        }
    )

    response = {
        'statusCode': 200,
        'body': json.dumps(result.get('Item'), cls=decimalencoder.DecimalEncoder)
    }
    return response
