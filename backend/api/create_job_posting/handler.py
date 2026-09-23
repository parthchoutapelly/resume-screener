def lambda_handler(event, context):
    return {
        "statusCode": 501,
        "headers": {"Content-Type": "application/json"},
        "body": '{"error":{"code":"NOT_IMPLEMENTED","message":"Stub — see docs/02-ingestion-pipeline.md or docs/03-scoring-and-api.md"}}',
    }
