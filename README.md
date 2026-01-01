# Multi-Cloud AI Agent for Automated Ticket Resolution

An multi-cloud AI agent system that automates support ticket resolution by leveraging distributed cloud services across Azure, AWS, and Pinecone. The system performs intent classification, knowledge retrieval, and response generation through coordinated agent workflows.

## Architecture Overview

This system demonstrates a true multi-cloud architecture where each cloud provider handles specific capabilities:

- **Azure Cognitive Services**: Natural language processing for entity extraction, intent classification, and sentiment analysis using Text Analytics API
- **AWS EC2**: Large language model inference using Ollama (qwen2.5:3b model) for automated response generation
- **AWS RDS**: PostgreSQL database for persistent ticket and audit trail storage
- **Pinecone**: Vector database providing semantic search and retrieval-augmented generation
- **LangGraph**: Multi-agent orchestration framework coordinating the workflow between specialized agents
- **Terraform**: Infrastructure as code for reproducible cloud resource deployment

## Technology Stack

### Application Framework

- **FastAPI**: High-performance REST API with automatic OpenAPI documentation
- **Pydantic v2**: Data validation and settings management with type safety
- **SQLAlchemy 2.0**: Modern Python SQL toolkit and ORM

### Machine Learning & AI

- **Azure Text Analytics**: Cloud-native NLP service for text understanding
- **Ollama qwen2.5:3b**: Open-source language model for response generation
- **SentenceTransformers**: all-MiniLM-L6-v2 model for semantic embeddings (384 dimensions)
- **Pinecone**: Managed vector database for similarity search

### Agent Orchestration

- **LangGraph 0.4.0**: State machine-based agent workflow coordination
- **Custom Agent Architecture**: Four specialized agents (NLP, Retrieval, Drafting, Supervisor)

## Project Structure

```
app/
├── api/
│   ├── main.py                 # FastAPI application
│   └── routes/
│       ├── tickets.py          # Ticket endpoints
│       └── health.py           # Health checks
├── agents/
│   ├── azure_nlp_agent.py      # Intent + entity extraction
│   ├── retrieval_agent.py      # Pinecone RAG
│   ├── drafting_agent.py       # AWS LLM response
│   └── supervisor.py           # LangGraph orchestrator
├── db/
│   ├── models.py               # SQLAlchemy models
│   ├── session.py              # Database connections
│   └── init_db.py              # DB initialization
├── embeddings/
│   ├── embed.py                # Sentence transformers
│   └── pinecone_client.py      # Pinecone operations
├── schemas/
│   ├── ticket.py               # Ticket schemas
│   └── response.py             # Response schemas
└── config.py                   # Configuration management

infra/
├── aws/
│   ├── rds.tf                  # PostgreSQL database
│   └── ec2_ollama.tf           # Ollama EC2 instance
├── azure/
    └── cognitive_services.tf  # Text Analytics


tests/
├── test_agents.py              # Agent unit tests
├── test_rag.py                 # RAG tests
└── test_integration.py         # API integration tests
```

## Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Configure environment variables:

```bash
cp .env.example .env
# Edit .env with your credentials
```

3. Initialize database:

```bash
python app/db/init_db.py
```

4. Start the API server:

```bash
uvicorn app.api.main:app --reload
```

## System Workflow

The system processes support tickets through a coordinated multi-agent pipeline:

1. **Ticket Submission**: Client submits ticket via REST API endpoint
2. **Persistence**: Ticket stored in PostgreSQL database with timestamp and metadata
3. **Agent Orchestration**: LangGraph supervisor initiates four-stage processing pipeline
   - **Stage 1 - NLP Analysis**: Azure Text Analytics performs entity extraction, intent classification, and sentiment analysis
   - **Stage 2 - Knowledge Retrieval**: Semantic search in Pinecone vector database retrieves relevant documentation (similarity threshold: 0.65)
   - **Stage 3 - Response Generation**: Ollama LLM generates contextual response using retrieved knowledge and ticket content
   - **Stage 4 - Quality Evaluation**: Supervisor assesses response confidence and determines if human review is required
4. **Audit Trail**: All agent decisions and intermediate outputs logged to database
5. **Response Delivery**: Client receives drafted response with confidence score, citations, and processing metadata

## Prerequisites

- Python 3.9+
- Azure subscription with Cognitive Services access
- AWS account with EC2 and RDS permissions
- Pinecone account and API key
- Terraform 1.0+ (for infrastructure deployment)

## Local Development Setup

1. Clone the repository:

```bash
git clone https://github.com/pallavisharma6802/Multi-Cloud-AI-Agent-for-Ticket-Resolution.git
cd Multi-Cloud-AI-Agent-for-Ticket-Resolution
```

2. Create and activate virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Configure environment variables:

```bash
cp .env.example .env
```

Edit `.env` with your cloud credentials:

```
AZURE_TEXT_ANALYTICS_ENDPOINT=https://eastus.api.cognitive.microsoft.com/
AZURE_TEXT_ANALYTICS_KEY=your_azure_key
PINECONE_API_KEY=your_pinecone_key
PINECONE_ENVIRONMENT=us-east-1
OLLAMA_BASE_URL=http://your-ec2-ip:11434
DATABASE_URL=postgresql://user:pass@host:5432/db
```

5. Initialize database schema:

```bash
python app/db/init_db.py
```

6. Seed knowledge base with sample documents:

```bash
python seed_kb.py
```

7. Start the application server:

```bash
./start_server.sh
```

8. Access API documentation at `http://localhost:8000/docs`

## Infrastructure Deployment

### Deploy Azure Cognitive Services

```bash
cd infra/azure
terraform init
terraform apply -var="azure_subscription_id=your_subscription_id"
```

Output provides Text Analytics endpoint and API key.

### Deploy AWS Infrastructure

Creates VPC, RDS PostgreSQL instance, and EC2 with Ollama auto-installation:

```bash
cd infra/aws
terraform init
terraform apply -var="db_username=admin" -var="db_password=SecurePass123!"
```

Wait 5-10 minutes for resources to provision. EC2 user data script automatically installs Ollama and pulls qwen2.5:3b model.

### Verify Deployment

Check Ollama availability:

```bash
curl http://your-ec2-ip:11434/api/tags
```

Test RDS connection:

```bash
psql -h your-rds-endpoint -U admin -d tickets_db
```

## API Reference

### Create Ticket

**Endpoint**: `POST /api/v1/tickets`

**Request Body**:

```json
{
  "title": "Cannot access VPN",
  "description": "I am trying to connect to the company VPN but keep getting connection timeout errors. I have tried restarting my computer but the issue persists.",
  "user_email": "user@company.com",
  "category": "it_support",
  "priority": "high"
}
```

**Response**:

```json
{
  "ticket_id": "uuid",
  "status": "open",
  "intent": "technical_issue",
  "priority": "urgent",
  "confidence": 0.66,
  "drafted_response": "Hello, I understand you're having trouble...",
  "knowledge_base_docs": [
    {
      "doc_id": "doc-002",
      "content": "VPN Troubleshooting Guide...",
      "similarity_score": 0.68
    }
  ],
  "requires_human_review": true,
  "agent_decisions": [
    {
      "agent_name": "azure_nlp_agent",
      "action": "analyze_intent_and_entities",
      "timestamp": "2025-12-29T18:21:15Z"
    }
  ],
  "created_at": "2025-12-29T18:21:14Z"
}
```

### Get Ticket

**Endpoint**: `GET /api/v1/tickets/{ticket_id}`

Returns full ticket details including all processing history.

### List Tickets

**Endpoint**: `GET /api/v1/tickets?status=open&limit=50&offset=0`

Query parameters:

- `status`: Filter by ticket status (open, resolved, pending)
- `limit`: Number of results per page (default: 50)
- `offset`: Pagination offset (default: 0)

### Health Check

**Endpoint**: `GET /health`

Returns service status and component health checks.

## Testing

Run the complete test suite:

```bash
pytest tests/ -v
```

Test individual components:

```bash
pytest tests/test_agents.py -v      # Agent unit tests
pytest tests/test_rag.py -v          # RAG and embeddings tests
pytest tests/test_integration.py -v  # API integration tests
```

Run end-to-end system test:

```bash
python test_ticket.py
```

## System Architecture Details

### Agent Pipeline

1. **Azure NLP Agent** (`app/agents/azure_nlp_agent.py`)

   - Entity extraction using Azure Text Analytics
   - Intent classification via keyword matching and sentiment analysis
   - Priority determination based on sentiment and urgency indicators
   - Fallback logic for API failures

2. **Retrieval Agent** (`app/agents/retrieval_agent.py`)

   - Generates semantic embeddings using SentenceTransformers
   - Performs vector similarity search in Pinecone
   - Filters results by similarity threshold (0.65)
   - Returns top-k relevant documents with scores

3. **Drafting Agent** (`app/agents/drafting_agent.py`)

   - Constructs prompts with ticket context and retrieved knowledge
   - Calls Ollama API for response generation
   - Calculates confidence based on knowledge base coverage
   - Handles timeout and error scenarios

4. **Supervisor Agent** (`app/agents/supervisor.py`)
   - Orchestrates agent workflow using LangGraph state machine
   - Manages state transitions between processing stages
   - Evaluates final response quality
   - Determines human review requirement based on confidence thresholds

### Data Models

**Ticket** (`app/db/models.py`):

- Stores ticket metadata, content, and status
- Tracks intent classification and priority
- Links to agent decision logs and drafted responses

**AgentDecisionLog**:

- Records each agent's actions and outputs
- Maintains processing timestamp and metadata
- Enables audit trail and debugging

**DraftedResponseLog**:

- Persists LLM-generated responses
- Stores confidence scores and KB document references
- Tracks human review flags

### Configuration Management

All settings centralized in `app/config.py` using Pydantic Settings:

- Cloud service credentials and endpoints
- Database connection strings
- Model parameters and thresholds
- Logging and timeout configuration

Environment variables loaded from `.env` file with validation.

## Performance Considerations

- **Embedding Caching**: SentenceTransformers model loaded once per agent instance
- **Connection Pooling**: SQLAlchemy connection pools for database efficiency
- **Async Operations**: FastAPI async endpoints for concurrent request handling
- **Timeout Management**: Configurable timeouts prevent hanging requests (default: 120s)
- **Vector Index**: Pinecone provides sub-100ms similarity search

## Security Notes

- API keys stored in environment variables, never committed to version control
- RDS security groups restrict database access to VPC CIDR blocks
- EC2 security groups limit Ollama API to necessary ports
- Azure Text Analytics uses subscription key authentication
- All cloud credentials rotatable without code changes

## Key Features

- Multi-cloud architecture with clear separation of concerns across Azure, AWS, and Pinecone
- Retrieval-augmented generation providing knowledge-grounded responses
- Complete audit trail capturing all agent decisions and intermediate outputs
- Automatic intent classification, priority assignment, and sentiment analysis
- Confidence scoring with intelligent human review flagging
- PostgreSQL persistence ensuring durability of tickets and processing history
- RESTful API with automatic OpenAPI documentation
- Comprehensive test coverage including unit, integration, and end-to-end tests
- Infrastructure as code enabling reproducible deployments
- Graceful degradation with fallback logic for cloud service failures

## Project Status

Current implementation includes:

- Functional multi-cloud agent pipeline with Azure NLP, Pinecone RAG, and AWS Ollama
- Complete REST API with FastAPI
- Database persistence with SQLAlchemy and PostgreSQL/SQLite support
- Terraform configurations for AWS and Azure resource deployment
- Knowledge base seeding and vector indexing
- End-to-end testing and validation

Future enhancements:

- GCP Workflows integration for advanced orchestration
- Expanded knowledge base with domain-specific documentation
- Fine-tuned intent classification models
- Real-time monitoring and observability dashboards
- Horizontal scaling with load balancers and container orchestration
