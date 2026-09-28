# embedding/service.py
from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

app = FastAPI()
model = SentenceTransformer("all-MiniLM-L6-v2")

class EmbedRequest(BaseModel):
    texts: list[str]

class EmbedResponse(BaseModel):
    embeddings: list[list[float]]

@app.post("/embed", response_model=EmbedResponse)
def embed(request: EmbedRequest):
    vectors = model.encode(request.texts).tolist()
    return EmbedResponse(embeddings=vectors)