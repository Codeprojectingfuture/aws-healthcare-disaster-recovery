import json
import boto3
import hashlib
from datetime import datetime, timezone
import uuid

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')
cloudwatch = boto3.client('cloudwatch')

# Configuration
TABLE_NAME = 'HealthcarePatientRecords'
BACKUP_BUCKET = 'dr-healthcare-primary-ab-20250803'  # Replace with your bucket name

def lambda_handler(event, context):
    """
    Healthcare Data Processor for PIPEDA-compliant patient records
    Processes incoming healthcare data, validates compliance, and creates backups
    """
    
    try:
        # Parse incoming healthcare data
        if 'body' in event:
            healthcare_data = json.loads(event['body'])
        else:
            healthcare_data = event
        
        # Generate unique processing ID
        processing_id = str(uuid.uuid4())
        
        # Validate PIPEDA compliance
        compliance_result = validate_pipeda_compliance(healthcare_data)
        
        if not compliance_result['compliant']:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'PIPEDA compliance validation failed',
                    'issues': compliance_result['issues'],
                    'processing_id': processing_id
                })
            }
        
        # Process the healthcare record
        processed_record = process_healthcare_record(healthcare_data, processing_id)
        
        # Store in DynamoDB
        table = dynamodb.Table(TABLE_NAME)
        table.put_item(Item=processed_record)
        
        # Create backup in S3
        backup_result = create_s3_backup(processed_record, processing_id)
        
        # Send CloudWatch metrics
        send_metrics(processing_id, 'SUCCESS')
        
        # Return success response
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'X-Processing-ID': processing_id
            },
            'body': json.dumps({
                'message': 'Healthcare record processed successfully',
                'processing_id': processing_id,
                'patient_id': processed_record['PatientID'],
                'compliance_status': 'PIPEDA_COMPLIANT',
                'backup_location': backup_result['location'],
                'timestamp': processed_record['SystemMetadata']['lastModified']
            })
        }
        
    except Exception as e:
        # Error handling and logging
        error_id = str(uuid.uuid4())
        send_metrics(error_id, 'ERROR')
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Healthcare data processing failed',
                'error_id': error_id,
                'message': str(e)
            })
        }

def validate_pipeda_compliance(data):
    """Validate healthcare data against PIPEDA requirements"""
    issues = []
    
    # Check required fields
    required_fields = ['PatientData', 'ComplianceInfo']
    for field in required_fields:
        if field not in data:
            issues.append(f"Missing required field: {field}")
    
    # Check consent
    if 'ComplianceInfo' in data:
        if not data['ComplianceInfo'].get('consentGiven', False):
            issues.append("Patient consent not provided")
        
        if data['ComplianceInfo'].get('encryptionLevel') != 'AES-256':
            issues.append("Inadequate encryption level")
    
    # Check data retention policy
    if 'ComplianceInfo' in data and 'dataRetention' not in data['ComplianceInfo']:
        issues.append("Data retention policy not specified")
    
    return {
        'compliant': len(issues) == 0,
        'issues': issues
    }

def process_healthcare_record(data, processing_id):
    """Process and enrich healthcare record with metadata"""
    
    # Generate timestamp
    current_time = datetime.now(timezone.utc).isoformat()
    
    # Create processed record
    processed_record = {
        **data,
        'SystemMetadata': {
            'processingId': processing_id,
            'createdBy': 'HealthcareDataProcessor',
            'region': 'us-east-1',
            'lastModified': current_time,
            'backupStatus': 'replicated',
            'dataHash': hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        }
    }
    
    # Ensure compliance info is complete
    if 'ComplianceInfo' not in processed_record:
        processed_record['ComplianceInfo'] = {}
    
    processed_record['ComplianceInfo'].update({
        'pipedaCompliant': True,
        'auditTrail': 'enabled',
        'processedTimestamp': current_time
    })
    
    return processed_record

def create_s3_backup(record, processing_id):
    """Create encrypted backup in S3"""
    
    backup_key = f"lambda-processed/{record['PatientID']}/{processing_id}.json"
    
    s3.put_object(
        Bucket=BACKUP_BUCKET,
        Key=backup_key,
        Body=json.dumps(record, indent=2),
        ServerSideEncryption='AES256',
        Metadata={
            'processing-id': processing_id,
            'patient-id': record['PatientID'],
            'compliance': 'PIPEDA'
        }
    )
    
    return {
        'location': f"s3://{BACKUP_BUCKET}/{backup_key}",
        'encryption': 'AES256'
    }

def send_metrics(processing_id, status):
    """Send processing metrics to CloudWatch"""
    
    cloudwatch.put_metric_data(
        Namespace='HealthcareProcessing',
        MetricData=[
            {
                'MetricName': 'RecordsProcessed',
                'Dimensions': [
                    {
                        'Name': 'Status',
                        'Value': status
                    },
                    {
                        'Name': 'Region',
                        'Value': 'us-east-1'
                    }
                ],
                'Value': 1,
                'Unit': 'Count'
            }
        ]
    )
