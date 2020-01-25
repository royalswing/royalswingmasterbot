import json
import os
import logging
from achievements import decimalencoder

import boto3
dynamodb = boto3.resource('dynamodb')

logger = logging.getLogger()
if logger.handlers:
    for handler in logger.handlers:
        logger.removeHandler(handler)
logging.basicConfig(level=logging.INFO)


def list(event, context) -> dict:
    logger.info('Event: {}'.format(event))
    logger.info('Context: {}'.format(context))
    table = dynamodb.Table(os.environ['ACHIEVEMENTS_TABLE'])

    result = table.scan(
        AttributesToGet=[
            'user_id',
            'bonus',
            'created_at',
            'updated_at',
        ]
    )

    response = {
        "statusCode": 200,
        "body": json.dumps(result['Items'], cls=decimalencoder.DecimalEncoder)
    }
    return response
