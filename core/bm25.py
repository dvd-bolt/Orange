import os
import re
import math
from typing import Dict, List, Set, Tuple

class BM25Indexer:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_lengths: Dict[str, int] = {}  # doc_path -> length
        self.doc_term_freqs: Dict[str, Dict[str, int]] = {}  # doc_path -> {term -> count}
        self.term_doc_freqs: Dict[str, int] = {}  # term -> number of docs containing term
        self.total_docs = 0
        self.avg_doc_len = 0.0

    def tokenize(self, text: str) -> List[str]:
        # Cyrillic and Latin alphanumeric words
        return re.findall(r'\w+', text.lower())

    def add_document(self, doc_path: str, text: str):
        # Remove old version if it exists to allow safe re-indexing on file edit
        self.remove_document(doc_path)

        terms = self.tokenize(text)
        if not terms:
            return

        self.doc_lengths[doc_path] = len(terms)
        term_counts: Dict[str, int] = {}
        for term in terms:
            term_counts[term] = term_counts.get(term, 0) + 1

        self.doc_term_freqs[doc_path] = term_counts
        for term in term_counts:
            self.term_doc_freqs[term] = self.term_doc_freqs.get(term, 0) + 1

        self.total_docs += 1
        self._update_avg_len()

    def remove_document(self, doc_path: str):
        if doc_path in self.doc_lengths:
            del self.doc_lengths[doc_path]
            term_counts = self.doc_term_freqs.pop(doc_path, {})
            for term in term_counts:
                if term in self.term_doc_freqs:
                    self.term_doc_freqs[term] -= 1
                    if self.term_doc_freqs[term] <= 0:
                        del self.term_doc_freqs[term]
            self.total_docs -= 1
            self._update_avg_len()

    def _update_avg_len(self):
        if self.total_docs > 0:
            self.avg_doc_len = sum(self.doc_lengths.values()) / self.total_docs
        else:
            self.avg_doc_len = 0.0

    def index_vault(self, vault_path: str):
        print(f"[BM25] Indexing vault path: {vault_path}")
        self.doc_lengths.clear()
        self.doc_term_freqs.clear()
        self.term_doc_freqs.clear()
        self.total_docs = 0
        self.avg_doc_len = 0.0

        abs_vault_path = os.path.abspath(vault_path)
        if not os.path.exists(abs_vault_path):
            print(f"[BM25 Warning] Vault path does not exist: {abs_vault_path}")
            return

        for root, _, files in os.walk(abs_vault_path):
            for file in files:
                if file.endswith('.md'):
                    file_path = os.path.join(root, file)
                    # Ignore service files and dot folders
                    if any(part.startswith('.') for part in file_path.replace(abs_vault_path, '').split(os.sep)):
                        continue
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                        self.add_document(file_path, content)
                    except Exception as e:
                        print(f"[BM25 Warning] Failed to index {file_path}: {e}")
        print(f"[BM25] Indexed {self.total_docs} files. Avg doc length: {self.avg_doc_len:.2f}")

    def search(self, query: str, limit: int = 5) -> List[Tuple[str, float]]:
        query_terms = self.tokenize(query)
        if not query_terms or self.total_docs == 0:
            return []

        scores: Dict[str, float] = {}
        for term in query_terms:
            n_q = self.term_doc_freqs.get(term, 0)
            if n_q == 0:
                continue

            # Standard IDF formula
            idf = math.log((self.total_docs - n_q + 0.5) / (n_q + 0.5) + 1.0)

            for doc_path, term_counts in self.doc_term_freqs.items():
                f_q = term_counts.get(term, 0)
                if f_q == 0:
                    continue

                doc_len = self.doc_lengths[doc_path]
                denom = f_q + self.k1 * (1.0 - self.b + self.b * (doc_len / (self.avg_doc_len or 1.0)))
                score = idf * (f_q * (self.k1 + 1.0)) / denom
                scores[doc_path] = scores.get(doc_path, 0.0) + score

        sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_results[:limit]

# Global instance for easy import and sharing across modules
global_bm25_indexer = BM25Indexer()
