import requests
from app.config import settings
from app.schemas.response import KBDocument
from typing import List
import logging
import json

logger = logging.getLogger(__name__)


class DraftingAgent:
    
    def __init__(self):
        self.ollama_url = f"{settings.ollama_base_url}/api/generate"
        self.model = "qwen2.5:3b"
    
    def draft_response(
        self,
        ticket_title: str,
        ticket_description: str,
        intent: str,
        kb_documents: List[KBDocument]
    ) -> tuple[str, float]:
        logger.info(f"Drafting response for intent: {intent}")
        
        prompt = self._build_prompt(
            ticket_title=ticket_title,
            ticket_description=ticket_description,
            intent=intent,
            kb_documents=kb_documents
        )
        
        try:
            response_text = self._call_ollama(prompt)
            confidence = self._calculate_confidence(kb_documents, response_text)
            
            logger.info(f"Response drafted with confidence: {confidence:.2f}")
            return response_text, confidence
            
        except Exception as e:
            logger.error(f"Failed to draft response: {e}")
            raise
    
    def _build_prompt(
        self,
        ticket_title: str,
        ticket_description: str,
        intent: str,
        kb_documents: List[KBDocument]
    ) -> str:
        context = ""
        if kb_documents:
            context = "Relevant knowledge base articles:\n\n"
            for i, doc in enumerate(kb_documents, 1):
                context += f"[Article {i}] (Relevance: {doc.similarity_score:.2f})\n"
                context += f"{doc.content}\n\n"
        else:
            context = "No specific knowledge base articles found for this issue.\n\n"
        
        prompt = f"""You are a customer support agent helping resolve a support ticket.

Ticket Title: {ticket_title}
Ticket Description: {ticket_description}
Classified Intent: {intent}

{context}

Instructions:
- Provide a clear, helpful response to the user's issue
- Base your answer on the knowledge base articles provided when relevant
- Be professional, empathetic, and concise
- If the knowledge base doesn't have sufficient information, acknowledge this and suggest next steps
- Do not make up information not present in the knowledge base
- Keep the response under 300 words

Response:"""
        
        return prompt
    
    def _call_ollama(self, prompt: str, max_tokens: int = 500) -> str:
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": 0.7,
                    "top_p": 0.9
                }
            }
            
            response = requests.post(
                self.ollama_url,
                json=payload,
                timeout=settings.request_timeout_seconds
            )
            
            response.raise_for_status()
            result = response.json()
            
            return result.get("response", "").strip()
            
        except requests.exceptions.Timeout:
            logger.error("Ollama request timed out")
            raise Exception("LLM request timed out")
        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama request failed: {e}")
            raise Exception(f"Failed to connect to LLM: {e}")
    
    def _calculate_confidence(self, kb_documents: List[KBDocument], response_text: str) -> float:
        if not kb_documents:
            return 0.5
        
        avg_similarity = sum(doc.similarity_score for doc in kb_documents) / len(kb_documents)
        
        response_length = len(response_text.split())
        length_score = min(response_length / 200, 1.0)
        
        confidence = (avg_similarity * 0.7) + (length_score * 0.3)
        
        return round(confidence, 2)
