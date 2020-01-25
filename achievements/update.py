import json
import os
import logging
from datetime import datetime
from achievements import decimalencoder

import boto3
dynamodb = boto3.resource('dynamodb')


def update(event: dict, context) -> dict:
    data = json.loads(event['body'])
    if 'achievements' not in data:
        logging.error('Validation Failed')
        raise Exception("Couldn't update the todo item.")

    timestamp = str(datetime.utcnow())

    table = dynamodb.Table(os.environ['ACHIEVEMENTS_TABLE'])

    # возмём старые значения из базы
    result = table.get_item(
        Key={
            'user_id': int(event['pathParameters']['id'])
        }
    )
    bonus = result['Item']['bonus']
    achievements = result['Item']['achievements']
    for achievement in data['achievements']:
        bonus += int(data['achievements'][achievement].get('price', 0))
        if achievement in achievements:
            try:
                achievements[achievement]['added_at'].append(timestamp)
            except KeyError:
                achievements[achievement]['added_at'] = [timestamp]
        else:
            achievements[achievement] = data['achievements'][achievement]
            achievements[achievement]['added_at'] = [timestamp]

    result = table.update_item(
        Key={
            'user_id': int(event['pathParameters']['id'])
        },
        ExpressionAttributeValues={
            ':achievements': achievements,
            ':bonus': bonus,
            ':updated_at': timestamp
        },
        UpdateExpression='SET achievements = :achievements, '
                         'updated_at = :updated_at, '
                         'bonus = :bonus',
        ReturnValues='ALL_NEW',
    )

    response = {
        'statusCode': 200,
        'body': json.dumps(result['Attributes'], cls=decimalencoder.DecimalEncoder)
    }
    return response

