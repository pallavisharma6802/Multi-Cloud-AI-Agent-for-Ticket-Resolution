#!/bin/bash
set -e

echo "=================================="
echo "Multi-Cloud Infrastructure Deployment"
echo "=================================="
echo ""

PROJECT_ROOT="/Users/pallavisharma/Desktop/projects/Multi-Cloud-AI-Agent-for-Ticket-Resolution"
cd "$PROJECT_ROOT"

# Load environment variables
source .env

echo "Step 1: Deploying Azure Cognitive Services..."
echo "----------------------------------------------"
cd infra/azure

# Create tfvars file
cat > terraform.tfvars <<EOF
azure_subscription_id = "$AZURE_SUBSCRIPTION_ID"
EOF

terraform init -input=false
terraform apply -auto-approve \
  -var="azure_subscription_id=$AZURE_SUBSCRIPTION_ID"

# Get Azure outputs
AZURE_ENDPOINT=$(terraform output -raw text_analytics_endpoint 2>/dev/null || echo "")
AZURE_KEY=$(terraform output -raw text_analytics_key 2>/dev/null || echo "")

echo ""
echo "Azure Deployment Complete!"
echo "Endpoint: $AZURE_ENDPOINT"
echo ""

echo "Step 2: Deploying AWS Infrastructure (VPC, RDS, EC2 with Ollama)..."
echo "--------------------------------------------------------------------"
cd "$PROJECT_ROOT/infra/aws"

terraform init -input=false
terraform apply -auto-approve \
  -var="db_username=postgres_admin" \
  -var="db_password=SecurePassword123!"

# Get AWS outputs
OLLAMA_URL=$(terraform output -raw ollama_url 2>/dev/null || echo "")
RDS_ENDPOINT=$(terraform output -raw rds_endpoint 2>/dev/null || echo "")

echo ""
echo "AWS Deployment Complete!"
echo "Ollama URL: $OLLAMA_URL"
echo "RDS Endpoint: $RDS_ENDPOINT"
echo ""

echo "Step 3: Updating .env file with actual endpoints..."
echo "----------------------------------------------------"
cd "$PROJECT_ROOT"

# Update .env file
if [ -n "$AZURE_ENDPOINT" ]; then
  sed -i.bak "s|AZURE_TEXT_ANALYTICS_ENDPOINT=.*|AZURE_TEXT_ANALYTICS_ENDPOINT=$AZURE_ENDPOINT|" .env
fi

if [ -n "$AZURE_KEY" ]; then
  sed -i.bak "s|AZURE_TEXT_ANALYTICS_KEY=.*|AZURE_TEXT_ANALYTICS_KEY=$AZURE_KEY|" .env
fi

if [ -n "$OLLAMA_URL" ]; then
  sed -i.bak "s|OLLAMA_BASE_URL=.*|OLLAMA_BASE_URL=$OLLAMA_URL|" .env
fi

if [ -n "$RDS_ENDPOINT" ]; then
  sed -i.bak "s|DATABASE_URL=.*|DATABASE_URL=postgresql://postgres_admin:SecurePassword123!@${RDS_ENDPOINT}:5432/tickets_db|" .env
fi

rm -f .env.bak

echo ""
echo "=================================="
echo "DEPLOYMENT COMPLETE!"
echo "=================================="
echo ""
echo "Azure Text Analytics Endpoint: $AZURE_ENDPOINT"
echo "AWS Ollama URL: $OLLAMA_URL"
echo "AWS RDS Endpoint: $RDS_ENDPOINT"
echo ""
echo "Your .env file has been updated with the actual endpoints."
echo ""
echo "NOTE: Wait 2-3 minutes for EC2 to finish installing Ollama,"
echo "then run: ./test_ticket.py"
echo ""
