# embedding/service.py
from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
from fastembed import SparseTextEmbedding

app = FastAPI()
model = SentenceTransformer("all-MiniLM-L6-v2")
sparse_model = SparseTextEmbedding("Qdrant/bm25", disable_stemmer=True)

class EmbedRequest(BaseModel):
    texts: list[str]

class SparseVector(BaseModel):
    indices: list[int]
    values: list[float]

class EmbedResponse(BaseModel):
    embeddings: list[list[float]]
    sparse_embeddings: list[SparseVector]

@app.post("/embed", response_model=EmbedResponse)
def embed(request: EmbedRequest):
    vectors = model.encode(request.texts).tolist()

    sparse_vectors = []
    for sparse in sparse_model.embed(request.texts):
        sparse_vectors.append(
            SparseVector(indices=sparse.indices.tolist(), values=sparse.values.tolist())
        )

    return EmbedResponse(embeddings=vectors, sparse_embeddings=sparse_vectors)