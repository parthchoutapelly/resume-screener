"""Unit tests for rs_common.ddb (R-DATA-01: Decimal in/out, never float)."""

from decimal import Decimal

import boto3
import botocore.exceptions
import pytest
from moto import mock_aws

from rs_common.ddb import conditional_update, from_decimal, to_decimal


def test_to_decimal_converts_float():
    assert to_decimal(71.35) == Decimal("71.3")  # rounded to 1dp per spec
    assert isinstance(to_decimal(71.3), Decimal)


def test_to_decimal_passes_through_non_float():
    assert to_decimal(5) == 5
    assert isinstance(to_decimal(5), int)
    assert to_decimal("aws") == "aws"
    assert to_decimal(None) is None
    assert to_decimal(True) is True


def test_to_decimal_recurses_lists_and_dicts():
    assert to_decimal([1.5, 2, "x"]) == [Decimal("1.5"), 2, "x"]
    assert to_decimal({"a": 1.25, "b": [2.5]}) == {"a": Decimal("1.2"), "b": [Decimal("2.5")]}


def test_from_decimal_converts_to_float():
    assert from_decimal(Decimal("71.3")) == 71.3
    assert isinstance(from_decimal(Decimal("71.3")), float)


def test_from_decimal_recurses():
    assert from_decimal({"a": Decimal("1.5"), "b": [Decimal("2.5"), 3]}) == {"a": 1.5, "b": [2.5, 3]}


def test_round_trip():
    original = {"score": 71.3, "count": 4, "name": "x"}
    assert from_decimal(to_decimal(original)) == original


@mock_aws
def test_conditional_update_returns_true_on_success():
    ddb = boto3.resource("dynamodb", region_name="ap-south-1")
    table = ddb.create_table(
        TableName="t",
        KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    table.put_item(Item={"id": "1", "status": "pending"})
    ok = conditional_update(
        table,
        Key={"id": "1"},
        UpdateExpression="SET #s = :v",
        ConditionExpression="#s = :old",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":v": "parsed", ":old": "pending"},
    )
    assert ok is True
    assert table.get_item(Key={"id": "1"})["Item"]["status"] == "parsed"


@mock_aws
def test_conditional_update_returns_false_not_raises_on_condition_failure():
    ddb = boto3.resource("dynamodb", region_name="ap-south-1")
    table = ddb.create_table(
        TableName="t",
        KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    table.put_item(Item={"id": "1", "status": "parsed"})  # already parsed
    ok = conditional_update(
        table,
        Key={"id": "1"},
        UpdateExpression="SET #s = :v",
        ConditionExpression="#s = :old",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":v": "error", ":old": "pending"},  # condition won't hold
    )
    assert ok is False
    assert table.get_item(Key={"id": "1"})["Item"]["status"] == "parsed"  # unchanged


@mock_aws
def test_conditional_update_reraises_other_errors():
    ddb = boto3.resource("dynamodb", region_name="ap-south-1")
    table = ddb.create_table(
        TableName="t",
        KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    with pytest.raises(botocore.exceptions.ClientError):
        conditional_update(table, Key={"id": "1"}, UpdateExpression="SET nonsense syntax !!!")
