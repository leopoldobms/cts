import uuid
import time
import json
import boto3
import traceback
from datetime import datetime
from botocore.client import Config
from packages.common.constants import (
    AWS_DELIVERY_STREAM,
    AWS_REGION,
    DEVELOPMENT_ENVIRONMENTS,
    APP_ENV,
)


class Storage:
    def store_exception(exception, data={}):

        data["error_id"] = str(uuid.uuid4())
        data["date"] = str(datetime.now())
        data["exceptionMessage"] = str(exception)
        data["exceptionTraceback"] = traceback.format_exc()
        print(data["exceptionTraceback"])

        client = boto3.client("firehose", region_name=AWS_REGION)
        aws_response = client.put_record(
            DeliveryStreamName=AWS_DELIVERY_STREAM,
            Record={"Data": json.dumps(data).encode("UTF-8")},
        )

        response = {}
        response['error_id'] = data["error_id"]

        return response

