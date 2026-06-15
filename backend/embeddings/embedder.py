import os
from sentence_transformers import SentenceTransformer

# Singleton instance for loading the embedding model once
_model_instance = None

def get_embedder_model():
    """
    Loads and returns the SentenceTransformer embedding model.
    """
    global _model_instance
    if _model_instance is None:
        # Load embedding model name from environment or fall back to default multilingual model
        model_name = os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
        print(f"[Embedder] Loading SentenceTransformer: {model_name}...")
        _model_instance = SentenceTransformer(model_name)
        print("[Embedder] Model successfully loaded.")
    return _model_instance

def generate_embeddings(texts):
    """
    Generates list embeddings for a collection of document texts.
    """
    model = get_embedder_model()
    # Ensure correct list representation
    if isinstance(texts, str):
        texts = [texts]
    return model.encode(texts, show_progress_bar=False).tolist()

def generate_query_embedding(query_text):
    """
    Generates embedding vector for a single query string.
    """
    model = get_embedder_model()
    return model.encode(query_text).tolist()
