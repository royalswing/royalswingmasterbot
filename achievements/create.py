import os
import json
import logging
import time
from datetime import datetime

import boto3
dynamodb = boto3.resource('dynamodb')


def create(event: dict, context) -> dict:
    data = json.loads(event['body'])
    if 'user_id' not in data:
        logging.error('Validation Failed')
        raise Exception("Couldn't create the todo item.")

    timestamp = str(datetime.utcnow())

    table = dynamodb.Table(os.environ['ACHIEVEMENTS_TABLE'])

    # создадим пользовательскую модель с достижениями
    item = {
        'user_id': data['user_id'],
        'bonus': data.get('bonus', 0),
        # Приверно так должен заполняться профиль пользователя
        # 'achievements': {
        #     'bday': {
        #         'name': 'Хороший возраст!',
        #         'description': 'В вашем аккаунте должен быть указан возраст.',
        #         'price': 20,
        #         'ratio': 1,
        #         'added_at': []
        #     },
        # },
        'achievements': data.get('achievements', {}),
        'created_at': timestamp,
        'updated_at': timestamp,
    }

    table.put_item(Item=item)

    response = {
        'statusCode': 201,
        'body': json.dumps(item)
    }
    return response
