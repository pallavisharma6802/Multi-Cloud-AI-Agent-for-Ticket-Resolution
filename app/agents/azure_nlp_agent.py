from azure.ai.textanalytics import TextAnalyticsClient
from azure.core.credentials import AzureKeyCredential
from app.config import settings
from app.schemas.ticket import TicketIntentClassification, TicketPriority
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)


class AzureNLPAgent:
    
    def __init__(self):
        self.client = TextAnalyticsClient(
            endpoint=settings.azure_text_analytics_endpoint,
            credential=AzureKeyCredential(settings.azure_text_analytics_key)
        )
    
    def analyze_ticket(self, title: str, description: str) -> TicketIntentClassification:
        text = f"{title}. {description}"
        
        entities = self._extract_entities(text)
        sentiment = self._analyze_sentiment(text)
        key_phrases = self._extract_key_phrases(text)
        
        intent, confidence = self._classify_intent(key_phrases, entities)
        priority = self._determine_priority(sentiment, key_phrases, entities)
        
        logger.info(f"Azure NLP analysis complete: intent={intent}, priority={priority}, confidence={confidence}")
        
        return TicketIntentClassification(
            intent=intent,
            confidence=confidence,
            entities=entities,
            sentiment=sentiment,
            priority=priority
        )
    
    def _extract_entities(self, text: str) -> List[Dict]:
        try:
            response = self.client.recognize_entities([text])[0]
            
            if response.is_error:
                logger.error(f"Entity extraction error: {response.error}")
                return []
            
            entities = []
            for entity in response.entities:
                entities.append({
                    "text": entity.text,
                    "category": entity.category,
                    "subcategory": entity.subcategory,
                    "confidence": entity.confidence_score
                })
            
            return entities
            
        except Exception as e:
            logger.error(f"Entity extraction failed: {e}")
            return []
    
    def _analyze_sentiment(self, text: str) -> str:
        try:
            response = self.client.analyze_sentiment([text])[0]
            
            if response.is_error:
                logger.error(f"Sentiment analysis error: {response.error}")
                return "neutral"
            
            return response.sentiment
            
        except Exception as e:
            logger.error(f"Sentiment analysis failed: {e}")
            return "neutral"
    
    def _extract_key_phrases(self, text: str) -> List[str]:
        try:
            response = self.client.extract_key_phrases([text])[0]
            
            if response.is_error:
                logger.error(f"Key phrase extraction error: {response.error}")
                return []
            
            return list(response.key_phrases)
            
        except Exception as e:
            logger.error(f"Key phrase extraction failed: {e}")
            return []
    
    def _classify_intent(self, key_phrases: List[str], entities: List[Dict]) -> tuple[str, float]:
        key_phrases_lower = [kp.lower() for kp in key_phrases]
        
        intent_keywords = {
            "password_reset": ["password", "reset", "forgot", "login", "access", "credentials"],
            "technical_issue": ["error", "bug", "crash", "broken", "not working", "failed"],
            "account_issue": ["account", "billing", "subscription", "payment", "invoice"],
            "feature_request": ["feature", "request", "need", "add", "implement", "enhancement"],
            "question": ["how", "what", "why", "when", "where", "question", "help"],
            "complaint": ["slow", "bad", "worst", "disappointed", "frustrated", "unhappy"]
        }
        
        intent_scores = {}
        
        for intent, keywords in intent_keywords.items():
            score = 0
            for keyword in keywords:
                if any(keyword in phrase for phrase in key_phrases_lower):
                    score += 1
            
            if score > 0:
                intent_scores[intent] = score
        
        if not intent_scores:
            return ("general_inquiry", 0.5)
        
        best_intent = max(intent_scores, key=intent_scores.get)
        max_score = intent_scores[best_intent]
        total_keywords = len(intent_keywords[best_intent])
        confidence = min(0.5 + (max_score / total_keywords) * 0.5, 0.95)
        
        return (best_intent, confidence)
    
    def _determine_priority(self, sentiment: str, key_phrases: List[str], entities: List[Dict]) -> TicketPriority:
        key_phrases_lower = [kp.lower() for kp in key_phrases]
        
        urgent_keywords = ["urgent", "emergency", "critical", "asap", "immediately", "down", "outage"]
        high_keywords = ["important", "priority", "soon", "blocked", "cannot", "unable"]
        
        has_urgent = any(keyword in phrase for phrase in key_phrases_lower for keyword in urgent_keywords)
        has_high = any(keyword in phrase for phrase in key_phrases_lower for keyword in high_keywords)
        
        if has_urgent or sentiment == "negative":
            return TicketPriority.URGENT
        elif has_high:
            return TicketPriority.HIGH
        elif sentiment == "neutral":
            return TicketPriority.MEDIUM
        else:
            return TicketPriority.LOW
