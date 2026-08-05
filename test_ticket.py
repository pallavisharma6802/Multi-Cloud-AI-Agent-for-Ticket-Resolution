#!/usr/bin/env python3
"""Manual live smoke-test script -- NOT part of the pytest suite.

Requires real credentials in .env (Azure Text Analytics, Pinecone, a running
Ollama server) and a seeded knowledge base (`python seed_kb.py --pack it_saas`).
Automated tests that don't need live services live in tests/ (see
tests/test_supervisor_graph.py for the mocked equivalent of this flow).
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import argparse
import json
import logging

from app.agents.supervisor import SupervisorAgent
from app.schemas.ticket import TicketCreate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_ticket_processing(domain_pack: str, title: str, description: str):
    ticket_data = TicketCreate(
        title=title,
        description=description,
        user_email="john.doe@example.com",
        domain_pack=domain_pack,
    )

    logger.info(f"Ticket: {ticket_data.title}")
    logger.info(f"Description: {ticket_data.description}")
    logger.info(f"Domain pack: {domain_pack}")
    logger.info("\nProcessing ticket through the agentic pipeline...\n")

    supervisor = SupervisorAgent()
    result = supervisor.process_ticket(
        ticket_id="TEST-001",
        title=ticket_data.title,
        description=ticket_data.description,
        domain_pack_id=domain_pack,
    )

    logger.info("\n" + "=" * 80)
    logger.info("TICKET RESOLUTION COMPLETE")
    logger.info("=" * 80)

    logger.info(f"\nTicket ID: {result.ticket_id}")
    logger.info(f"Confidence: {result.confidence:.2f}")
    logger.info(f"Requires Human Review: {result.requires_human_review}")
    logger.info(f"\nFull trace:\n{json.dumps(result.trace, indent=2, default=str)}")

    logger.info(f"\nRetrieved {len(result.kb_documents)} relevant KB documents:")
    for doc in result.kb_documents:
        logger.info(f"  - {doc.doc_id} (score: {doc.similarity_score:.2f})")

    logger.info(f"\nAgent Decisions ({len(result.agent_decisions)} steps):")
    for decision in result.agent_decisions:
        logger.info(f"  - {decision.agent_name}: {decision.action}")

    logger.info(f"\n{'=' * 80}")
    logger.info("DRAFTED RESPONSE:")
    logger.info("=" * 80)
    print(result.draft_text)
    logger.info("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", default="it_saas", choices=["it_saas"])
    parser.add_argument("--title", default="Cannot access VPN")
    parser.add_argument(
        "--description",
        default="I am trying to connect to the company VPN but keep getting connection timeout errors. "
        "I have tried restarting my computer but the issue persists.",
    )
    args = parser.parse_args()
    test_ticket_processing(args.pack, args.title, args.description)
