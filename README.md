# Multi-Cloud AI Agent for Ticket Resolution

A multi-agent system that automates support ticket resolution across Azure, AWS, and Pinecone — handling intent classification, RAG-based knowledge retrieval, and LLM response drafting through a LangGraph orchestration pipeline.

## Tech Stack

| Layer | Tools |
|---|---|
| Agent Orchestration | LangGraph 0.4.0 (state machine workflow) |
| NLP | Azure Text Analytics (intent, entities, sentiment) |
| LLM Inference | Ollama qwen2.5:3b on AWS EC2 |
| Vector Search | Pinecone (all-MiniLM-L6-v2, 384-dim, similarity threshold 0.65) |
| Database | PostgreSQL on AWS RDS (SQLAlchemy 2.0) |
| API | FastAPI + Pydantic v2 |
| Infrastructure | Terraform (AWS + Azure) |

## Agent Pipeline
```
POST /tickets → PostgreSQL → LangGraph Supervisor
                                    ↓
                    [1] Azure NLP → intent + entities + sentiment
                    [2] Pinecone  → top-k relevant docs (RAG)
                    [3] Ollama    → draft response from context
                    [4] Supervisor → confidence score + human review flag
                                    ↓
                         response + citations + audit trail
```

Four specialized agents, each owning one stage. All decisions logged to DB for full audit trail.

## Sample Response
```json
{
  "ticket_id": "uuid",
  "intent": "technical_issue",
  "confidence": 0.66,
  "drafted_response": "Hello, I understand you're having trouble...",
  "knowledge_base_docs": [{ "doc_id": "doc-002", "similarity_score": 0.68 }],
  "requires_human_review": true,
  "agent_decisions": [{ "agent_name": "azure_nlp_agent", "action": "analyze_intent_and_entities" }]
}
```

## Quick Start
```bash
git clone https://github.com/pallavisharma6802/Multi-Cloud-AI-Agent-for-Ticket-Resolution.git
cd Multi-Cloud-AI-Agent-for-Ticket-Resolution

python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env  # add Azure, AWS, Pinecone credentials
python app/db/init_db.py
python seed_kb.py
./start_server.sh
# API docs at http://localhost:8000/docs
```

## Infrastructure (Terraform)
```bash
# Azure: Text Analytics
cd infra/azure && terraform init && terraform apply

# AWS: RDS + EC2 with Ollama auto-installed
cd infra/aws && terraform init && terraform apply
# EC2 user data pulls qwen2.5:3b automatically (~5-10 min)
```

## Project Structure
```
app/
├── agents/          # azure_nlp, retrieval, drafting, supervisor
├── api/             # FastAPI routes (tickets, health)
├── db/              # SQLAlchemy models + session
├── embeddings/      # SentenceTransformers + Pinecone client
└── config.py        # Pydantic settings

infra/
├── aws/             # rds.tf, ec2_ollama.tf
└── azure/           # cognitive_services.tf

tests/               # unit, RAG, integration
```

## Tests
```bash
pytest tests/ -v
python test_ticket.py  # end-to-end
```
