terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket         = "driftguard-terraform-state"
    key            = "infrastructure/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "driftguard-terraform-lock"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "DriftGuard"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

# ============================================================================
# VARIABLES
# ============================================================================

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "environment" {
  type    = string
  default = "production"
}

variable "api_image_uri" {
  type        = string
  description = "ECR image URI for the DriftGuard API"
}

variable "supabase_url" {
  type      = string
  sensitive = true
}

variable "supabase_service_key" {
  type      = string
  sensitive = true
}

variable "stripe_secret_key" {
  type      = string
  sensitive = true
}

variable "stripe_webhook_secret" {
  type      = string
  sensitive = true
}

# ============================================================================
# DYNAMODB — Time-series metrics storage
# ============================================================================

resource "aws_dynamodb_table" "metrics" {
  name         = "driftguard-metrics-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "model_endpoint_id"
  range_key    = "sort_key"

  attribute {
    name = "model_endpoint_id"
    type = "S"
  }

  attribute {
    name = "sort_key"
    type = "S"
  }

  attribute {
    name = "workspace_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "S"
  }

  global_secondary_index {
    name            = "workspace-timestamp-index"
    hash_key        = "workspace_id"
    range_key       = "timestamp"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Name = "driftguard-metrics"
  }
}

# ============================================================================
# ECR — Container registry for API
# ============================================================================

resource "aws_ecr_repository" "api" {
  name                 = "driftguard/api"
  image_tag_mutability = "MUTABLE"
  force_delete         = false

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# ============================================================================
# IAM — Lambda execution role
# ============================================================================

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "drift_detector_lambda" {
  name               = "driftguard-drift-detector-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "drift_detector_policy" {
  statement {
    sid = "DynamoDBAccess"
    actions = [
      "dynamodb:Query",
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:BatchWriteItem",
      "dynamodb:DeleteItem",
    ]
    resources = [
      aws_dynamodb_table.metrics.arn,
      "${aws_dynamodb_table.metrics.arn}/index/*",
    ]
  }

  statement {
    sid = "SNSPublish"
    actions = [
      "sns:Publish",
    ]
    resources = [aws_sns_topic.drift_alerts.arn]
  }

  statement {
    sid = "SESEmail"
    actions = [
      "ses:SendEmail",
      "ses:SendRawEmail",
    ]
    resources = ["*"]
  }

  statement {
    sid = "CloudWatchLogs"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:*:*:*"]
  }

  statement {
    sid = "BedrockRead"
    actions = [
      "bedrock:GetFoundationModel",
      "bedrock:ListFoundationModels",
    ]
    resources = ["*"]
  }

  statement {
    sid = "CloudWatchLogsRead"
    actions = [
      "logs:FilterLogEvents",
      "logs:GetLogEvents",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "drift_detector" {
  name   = "driftguard-drift-detector-policy"
  role   = aws_iam_role.drift_detector_lambda.id
  policy = data.aws_iam_policy_document.drift_detector_policy.json
}

# ============================================================================
# LAMBDA — Scheduled drift detection
# ============================================================================

resource "aws_lambda_function" "drift_detector" {
  function_name = "driftguard-drift-detector-${var.environment}"
  role          = aws_iam_role.drift_detector_lambda.arn
  package_type  = "Image"
  image_uri     = var.api_image_uri
  timeout       = 300
  memory_size   = 1024

  image_config {
    command = ["src.lambda_handler.handler"]
  }

  environment {
    variables = {
      ENVIRONMENT        = var.environment
      DYNAMO_TABLE_NAME  = aws_dynamodb_table.metrics.name
      SUPABASE_URL       = var.supabase_url
      SUPABASE_SERVICE_KEY = var.supabase_service_key
      SNS_TOPIC_ARN      = aws_sns_topic.drift_alerts.arn
    }
  }

  tracing_config {
    mode = "Active"
  }
}

# ============================================================================
# EVENTBRIDGE — Scheduled execution
# ============================================================================

resource "aws_cloudwatch_event_rule" "drift_check_schedule" {
  name                = "driftguard-drift-check-${var.environment}"
  description         = "Trigger drift detection checks every 15 minutes"
  schedule_expression = "rate(15 minutes)"
}

resource "aws_cloudwatch_event_target" "drift_check" {
  rule      = aws_cloudwatch_event_rule.drift_check_schedule.name
  target_id = "DriftDetectorLambda"
  arn       = aws_lambda_function.drift_detector.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.drift_detector.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.drift_check_schedule.arn
}

# ============================================================================
# SNS — Drift alert topic
# ============================================================================

resource "aws_sns_topic" "drift_alerts" {
  name = "driftguard-drift-alerts-${var.environment}"

  tags = {
    Name = "DriftGuard Drift Alerts"
  }
}

resource "aws_sns_topic_policy" "drift_alerts" {
  arn = aws_sns_topic.drift_alerts.arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowLambdaPublish"
        Effect    = "Allow"
        Principal = { AWS = aws_iam_role.drift_detector_lambda.arn }
        Action    = "sns:Publish"
        Resource  = aws_sns_topic.drift_alerts.arn
      }
    ]
  })
}

# ============================================================================
# CLOUDWATCH — Monitoring & alarms
# ============================================================================

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "driftguard-lambda-errors-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "DriftGuard drift detector Lambda error rate"

  dimensions = {
    FunctionName = aws_lambda_function.drift_detector.function_name
  }

  alarm_actions = [aws_sns_topic.drift_alerts.arn]
  ok_actions    = [aws_sns_topic.drift_alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "lambda_duration" {
  alarm_name          = "driftguard-lambda-duration-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Average"
  threshold           = 240000
  alarm_description   = "DriftGuard drift detector Lambda duration approaching timeout"

  dimensions = {
    FunctionName = aws_lambda_function.drift_detector.function_name
  }

  alarm_actions = [aws_sns_topic.drift_alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "dynamo_throttle" {
  alarm_name          = "driftguard-dynamo-throttle-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "ThrottledRequests"
  namespace           = "AWS/DynamoDB"
  period              = 300
  statistic           = "Sum"
  threshold           = 10
  alarm_description   = "DriftGuard DynamoDB throttling detected"

  dimensions = {
    TableName = aws_dynamodb_table.metrics.name
  }

  alarm_actions = [aws_sns_topic.drift_alerts.arn]
}

# ============================================================================
# OUTPUTS
# ============================================================================

output "dynamodb_table_name" {
  value = aws_dynamodb_table.metrics.name
}

output "dynamodb_table_arn" {
  value = aws_dynamodb_table.metrics.arn
}

output "ecr_repository_url" {
  value = aws_ecr_repository.api.repository_url
}

output "lambda_function_name" {
  value = aws_lambda_function.drift_detector.function_name
}

output "lambda_function_arn" {
  value = aws_lambda_function.drift_detector.arn
}

output "sns_topic_arn" {
  value = aws_sns_topic.drift_alerts.arn
}
