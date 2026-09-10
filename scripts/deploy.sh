#!/bin/bash

# Healthcare Disaster Recovery System Deployment Script
# Author: AWS Solutions Architect
# Date: 2025-08-03

set -e

PROJECT_NAME="healthcare-dr"
STACK_NAME="${PROJECT_NAME}-system"
REGION="us-east-1"

echo "🚀 Deploying Healthcare Disaster Recovery System..."
echo "Project: $PROJECT_NAME"
echo "Region: $REGION"
echo "Stack: $STACK_NAME"
echo ""

# Validate CloudFormation template
echo "📋 Validating CloudFormation template..."
aws cloudformation validate-template \
    --template-body file://cloudformation/infrastructure.yaml \
    --region $REGION

if [ $? -eq 0 ]; then
    echo "✅ Template validation successful"
else
    echo "❌ Template validation failed"
    exit 1
fi

# Deploy CloudFormation stack
echo ""
echo "🏗️ Deploying infrastructure stack..."
aws cloudformation deploy \
    --template-file cloudformation/infrastructure.yaml \
    --stack-name $STACK_NAME \
    --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
    --parameter-overrides \
        ProjectName=$PROJECT_NAME \
        Environment=production \
    --region $REGION \
    --tags \
        Project=$PROJECT_NAME \
        Environment=production \
        Purpose="Healthcare Disaster Recovery" \
        Compliance="PIPEDA"

if [ $? -eq 0 ]; then
    echo "✅ Infrastructure deployment successful"
else
    echo "❌ Infrastructure deployment failed"
    exit 1
fi

# Get stack outputs
echo ""
echo "📊 Retrieving stack outputs..."
BUCKET_NAME=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --query 'Stacks[0].Outputs[?OutputKey==`PrimaryBucketName`].OutputValue' \
    --output text \
    --region $REGION)

TABLE_NAME=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --query 'Stacks[0].Outputs[?OutputKey==`DynamoDBTableName`].OutputValue' \
    --output text \
    --region $REGION)

LAMBDA_ARN=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --query 'Stacks[0].Outputs[?OutputKey==`LambdaFunctionArn`].OutputValue' \
    --output text \
    --region $REGION)

echo "Primary Bucket: $BUCKET_NAME"
echo "DynamoDB Table: $TABLE_NAME"
echo "Lambda Function: $LAMBDA_ARN"

# Update Lambda function code
echo ""
echo "⚡ Updating Lambda function code..."
cd lambda-functions/healthcare-data-processor
zip -r function.zip . -x "*.git*" "*.DS_Store*"

aws lambda update-function-code \
    --function-name ${PROJECT_NAME}-data-processor \
    --zip-file fileb://function.zip \
    --region $REGION

if [ $? -eq 0 ]; then
    echo "✅ Lambda function update successful"
else
    echo "❌ Lambda function update failed"
    exit 1
fi

cd ../..

# Test the deployment
echo ""
echo "🧪 Testing deployment..."
aws lambda invoke \
    --function-name ${PROJECT_NAME}-data-processor \
    --payload file://test-data/sample-patient.json \
    --region $REGION \
    response.json

if [ $? -eq 0 ]; then
    echo "✅ Deployment test successful"
    echo "📄 Response saved to response.json"
else
    echo "❌ Deployment test failed"
fi

echo ""
echo "🎉 Deployment completed successfully!"
echo ""
echo "📋 Next Steps:"
echo "1. Verify S3 cross-region replication"
echo "2. Check DynamoDB Global Tables status"
echo "3. Monitor CloudWatch metrics"
echo "4. Run compliance audit"
echo ""
echo "🔗 Dashboard URL:"
aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --query 'Stacks[0].Outputs[?OutputKey==`DashboardURL`].OutputValue' \
    --output text \
    --region $REGION
