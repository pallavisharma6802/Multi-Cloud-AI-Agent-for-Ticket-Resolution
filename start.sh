#!/bin/bash
set -e

echo "Multi-Cloud AI Agent Setup"


cd /Users/pallavisharma/Desktop/projects/Multi-Cloud-AI-Agent-for-Ticket-Resolution

echo "[1/4] Activating virtual environment..."
source venv/bin/activate

echo "[2/4] Checking configuration..."
if [ -f ".env" ]; then
    echo ".env file found"
else
    echo ".env file not found!"
    exit 1
fi

echo "[3/4] Initializing database tables..."
echo "Creating PostgreSQL tables in RDS..."
python app/db/init_db.py

echo ""
echo "[4/4] Starting FastAPI server..."
echo "Server will be available at http://localhost:8000"
echo "API documentation at http://localhost:8000/docs"
echo ""
uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
