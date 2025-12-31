#!/usr/bin/env python3
"""Test script to create a ticket and see the full agent workflow"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.agents.supervisor import SupervisorAgent
from app.schemas.ticket import TicketCreate
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_ticket_processing():
    logger.info("Creating test ticket...")
    
    ticket_data = TicketCreate(
        title="Cannot access VPN",
        description="I am trying to connect to the company VPN but keep getting connection timeout errors. I have tried restarting my computer but the issue persists.",
        user_email="john.doe@company.com",
        category="it_support",
        priority="high"
    )
    
    logger.info(f"Ticket: {ticket_data.title}")
    logger.info(f"Description: {ticket_data.description}")
    logger.info("\nProcessing ticket through multi-cloud agent pipeline...\n")
    
    supervisor = SupervisorAgent()
    result = supervisor.process_ticket(
        ticket_id="TEST-001",
        title=ticket_data.title,
        description=ticket_data.description
    )
    
    logger.info("\n" + "="*80)
    logger.info("TICKET RESOLUTION COMPLETE")
    logger.info("="*80)
    
    logger.info(f"\nTicket ID: {result.ticket_id}")
    logger.info(f"Confidence: {result.confidence:.2f}")
    logger.info(f"Requires Human Review: {result.requires_human_review}")
    
    logger.info(f"\nRetrieved {len(result.kb_documents)} KB documents:")
    for doc in result.kb_documents:
        logger.info(f"  - {doc.doc_id} (score: {doc.similarity_score:.2f})")
    
    logger.info(f"\nAgent Decisions ({len(result.agent_decisions)} steps):")
    for decision in result.agent_decisions:
        logger.info(f"  - {decision.agent_name}: {decision.action}")
    
    logger.info(f"\n{'='*80}")
    logger.info("DRAFTED RESPONSE:")
    logger.info("="*80)
    print(result.draft_text)
    logger.info("="*80)

if __name__ == "__main__":
    test_ticket_processing()
