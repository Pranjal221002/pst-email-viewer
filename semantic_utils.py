import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")

class SemanticEmailIndex:
    def __init__(self):
        self.emails = []
        self.embeddings = None
        self.index = None
        self.pst_path = None  # Store last indexed file path
        self.model = SentenceTransformer("all-MiniLM-L6-v2")

    def build_index(self, emails):
        self.emails = emails
        texts =[(email.get("subject") or "") + " " + (email.get("body") or "") for email in emails]
        self.embeddings = self.model.encode(texts, convert_to_tensor=True)
        self.index = faiss.IndexFlatL2(self.embeddings.shape[1])
        self.index.add(self.embeddings.cpu().numpy())  

    def search(self, query, top_k=10):
        query_embedding = self.model.encode([query], convert_to_tensor=True)
        distances, indices = self.index.search(query_embedding.cpu().numpy(), top_k)
        return [self.emails[i] for i in indices[0]]

    def save(self, path_prefix):
        faiss.write_index(self.index, f"{path_prefix}.index")
        with open(f"{path_prefix}.meta", "wb") as f:
            import pickle
            pickle.dump(self.emails, f)

    def load(self, path_prefix):
        self.index = faiss.read_index(f"{path_prefix}.index")
        with open(f"{path_prefix}.meta", "rb") as f:
            import pickle
            self.emails = pickle.load(f)   