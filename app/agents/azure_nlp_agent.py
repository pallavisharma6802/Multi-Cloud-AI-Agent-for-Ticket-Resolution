"""Azure Text Analytics: NER, sentiment, and key phrases.

Returns raw NLPSignals only. Intent and priority are handled by
IntentPriorityAgent.
"""
import logging
from typing import Dict, List

from azure.ai.textanalytics import TextAnalyticsClient
from azure.core.credentials import AzureKeyCredential

from app.config import settings
from app.schemas.ticket import NLPSignals

logger = logging.getLogger(__name__)


class AzureNLPAgent:

    def __init__(self):
        self.client = TextAnalyticsClient(
            endpoint=settings.azure_text_analytics_endpoint,
            credential=AzureKeyCredential(settings.azure_text_analytics_key)
        )

    def analyze_ticket(self, title: str, description: str) -> NLPSignals:
        text = f"{title}. {description}"

        entities = self._extract_entities(text)
        sentiment = self._analyze_sentiment(text)
        key_phrases = self._extract_key_phrases(text)

        logger.info(
            f"Azure NLP signals extracted: {len(entities)} entities, "
            f"sentiment={sentiment}, {len(key_phrases)} key phrases"
        )

        return NLPSignals(
            entities=entities,
            sentiment=sentiment,
            key_phrases=key_phrases,
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
