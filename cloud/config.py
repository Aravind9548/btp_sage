"""Centralised configuration for the LocalStack cloud layer.

Every cloud module imports endpoint URLs, table names, and boto3 helpers
from here so nothing is repeated.
"""
from __future__ import annotations

import boto3

LOCALSTACK_ENDPOINT = "http://localhost:4566"
AWS_REGION = "us-east-1"
AWS_ACCESS_KEY_ID = "test"
AWS_SECRET_ACCESS_KEY = "test"

LEASE_TABLE = "SagaLeases"
SAGA_STATE_TABLE = "SagaState"
EVENT_LOG_TABLE = "EventLog"

SNS_TOPIC_PREFIX = "saga-"


def get_client(service: str, endpoint_url: str = LOCALSTACK_ENDPOINT):
    return boto3.client(
        service,
        endpoint_url=endpoint_url,
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )


def get_resource(service: str, endpoint_url: str = LOCALSTACK_ENDPOINT):
    return boto3.resource(
        service,
        endpoint_url=endpoint_url,
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )
