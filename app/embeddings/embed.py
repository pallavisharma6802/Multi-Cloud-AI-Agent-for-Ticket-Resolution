import json
import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List

import boto3
from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger(__name__)

# amazon.titan-embed-text-v2:0 supports 256/512/1024 output dimensions via
# the request body -- 512 keeps Pinecone storage/compute modest while still
# being a real, full-quality Titan embedding (not a truncated 256).
TITAN_EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"
TITAN_EMBED_DIMENSION = 512


class EmbeddingGenerator:
    """Calls Bedrock's Titan Embed model instead of loading a local
    SentenceTransformer. Avoids bundling torch/transformers (and the memory
    spike of loading a model into process memory) purely to turn text into
    vectors -- Bedrock is already the project's LLM backend, so this reuses
    the same credentials and billing model instead of adding a new one.
    """

    def __init__(self):
        self.dimension = TITAN_EMBED_DIMENSION
        self._client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
        logger.info(f"Embedding backend: Bedrock {TITAN_EMBED_MODEL_ID}, dimension={self.dimension}")

    def _embed_one(self, text: str) -> List[float]:
        body = json.dumps({"inputText": text, "dimensions": self.dimension, "normalize": True})
        # Titan's on-demand throughput quota is well below what 8 concurrent
        # workers can generate -- retry with jittered backoff on top of
        # boto3's own built-in retries rather than failing the whole batch.
        max_attempts = 6
        for attempt in range(max_attempts):
            try:
                response = self._client.invoke_model(modelId=TITAN_EMBED_MODEL_ID, body=body)
                payload = json.loads(response["body"].read())
                return payload["embedding"]
            except ClientError as e:
                if e.response.get("Error", {}).get("Code") != "ThrottlingException" or attempt == max_attempts - 1:
                    raise
                time.sleep((2 ** attempt) * 0.5 + random.uniform(0, 0.5))
        raise RuntimeError("unreachable")

    def generate_embedding(self, text: str) -> List[float]:
        try:
            return self._embed_one(text)
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise

    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        # Titan has no native batch-embed endpoint via invoke_model, so this
        # fans out individual calls over a small thread pool -- fast enough
        # for a one-time KB seed without risking per-account rate limits.
        try:
            with ThreadPoolExecutor(max_workers=3) as pool:
                return list(pool.map(self._embed_one, texts))
        except Exception as e:
            logger.error(f"Failed to generate batch embeddings: {e}")
            raise

    def get_dimension(self) -> int:
        return self.dimension
