from app.agents.retrieval_agent import RetrievalAgent
import logging

logging.basicConfig(level="INFO")
logger = logging.getLogger(__name__)

kb_documents = [
    {
        "id": "doc-001",
        "text": "To reset your password: 1) Go to the login page 2) Click 'Forgot Password' 3) Enter your email 4) Check your email for reset link 5) Click the link and create a new password. Password must be at least 8 characters with uppercase, lowercase, and numbers.",
        "category": "password_reset",
        "source": "password-reset-guide.md"
    },
    {
        "id": "doc-002",
        "text": "VPN connection issues: First, verify your internet connection is stable. Then check if VPN client is updated to latest version. Make sure firewall is not blocking VPN ports (1194 for OpenVPN, 500/4500 for IPSec). Try disconnecting and reconnecting. If issue persists, contact IT support.",
        "category": "technical_issue",
        "source": "vpn-troubleshooting.md"
    },
    {
        "id": "doc-003",
        "text": "Email access problems: If you cannot access your email, first verify your credentials are correct. Check if your account is locked due to multiple failed login attempts. Ensure your mailbox is not full. Try accessing from different device or browser. Clear browser cache and cookies.",
        "category": "technical_issue",
        "source": "email-access-guide.md"
    },
    {
        "id": "doc-004",
        "text": "Account billing and subscription: To view your subscription details, log into your account portal. Go to Settings > Billing. You can view invoices, update payment methods, and change subscription plans. Billing cycle is monthly and auto-renews on the same date each month.",
        "category": "account_issue",
        "source": "billing-guide.md"
    },
    {
        "id": "doc-005",
        "text": "Software installation guide: Before installing, check system requirements. Download installer from official website. Run installer as administrator. Follow on-screen prompts. Restart computer after installation. If installation fails, check antivirus is not blocking it.",
        "category": "technical_issue",
        "source": "installation-guide.md"
    }
]

def seed_knowledge_base():
    logger.info("Starting knowledge base seeding...")
    
    try:
        agent = RetrievalAgent()
        agent.index_knowledge_base(kb_documents)
        
        logger.info(f"Successfully indexed {len(kb_documents)} documents to Pinecone")
        
        test_query = "how to reset password"
        results = agent.retrieve_relevant_documents(test_query, top_k=2)
        
        logger.info(f"Test query: '{test_query}'")
        logger.info(f"Retrieved {len(results)} documents:")
        for doc in results:
            logger.info(f"  - {doc.doc_id}: {doc.similarity_score:.2f}")
        
        logger.info("Knowledge base seeding completed successfully!")
        
    except Exception as e:
        logger.error(f"Failed to seed knowledge base: {e}")
        raise

if __name__ == "__main__":
    seed_knowledge_base()
