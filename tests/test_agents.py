import pytest
from app.agents.azure_nlp_agent import AzureNLPAgent
from app.schemas.ticket import TicketPriority


@pytest.fixture
def azure_agent():
    return AzureNLPAgent()


def test_password_reset_intent(azure_agent):
    result = azure_agent.analyze_ticket(
        title="Can't login",
        description="I forgot my password and cannot access my account"
    )
    
    assert result.intent == "password_reset"
    assert result.confidence > 0.5
    assert result.sentiment in ["positive", "negative", "neutral"]


def test_urgent_priority_detection(azure_agent):
    result = azure_agent.analyze_ticket(
        title="Critical system outage",
        description="Our production system is down and users cannot access the service. This is urgent!"
    )
    
    assert result.priority == TicketPriority.URGENT


def test_entity_extraction(azure_agent):
    result = azure_agent.analyze_ticket(
        title="Issue with Office 365",
        description="I'm having problems with Microsoft Office 365 on Windows 10"
    )
    
    assert isinstance(result.entities, list)
