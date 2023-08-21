import pytest
import sys
import boto3
from http import HTTPStatus
from moto import mock_kinesis
sys.path.insert(1, "../..")
from packages.common.storage import Storage
from packages.common.constants import AWS_DELIVERY_STREAM


def create_stream(client, stream_name):
    return client.create_delivery_stream(
        DeliveryStreamName=stream_name,
        RedshiftDestinationConfiguration={
            'RoleARN': 'arn:aws:iam::123456789012:role/firehose_delivery_role',
            'ClusterJDBCURL': 'jdbc:redshift://host.amazonaws.com:5439/database',
            'CopyCommand': {
                'DataTableName': 'outputTable',
                'CopyOptions': "CSV DELIMITER ',' NULL '\\0'"
            },
            'Username': 'username',
            'Password': 'password',
            'S3Configuration': {
                'RoleARN': 'arn:aws:iam::123456789012:role/firehose_delivery_role',
                'BucketARN': 'arn:aws:s3:::kinesis-test',
                'Prefix': 'myFolder/',
                'BufferingHints': {
                    'SizeInMBs': 123,
                    'IntervalInSeconds': 124
                },
                'CompressionFormat': 'UNCOMPRESSED',
            }
        }
    )

@mock_kinesis
def test_successful_log_storage():
    client = boto3.client('firehose', region_name='us-east-1')
    create_stream(client, AWS_DELIVERY_STREAM)
    e = ValueError('Test')
    response = Storage.store_exception(e,{'Data': 'Test'})
    assert response['ResponseMetadata']['HTTPStatusCode'] == HTTPStatus.OK

@mock_kinesis
def test_failed_log_storage():
    with pytest.raises(Exception):
        e = ValueError('Test')
        response = Storage.store_exception(e,{'Data': 'Test'})

@mock_kinesis
def test_no_params_log_storage():
    with pytest.raises(TypeError):
        response = Storage.store_exception()