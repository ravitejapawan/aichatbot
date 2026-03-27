import json
import re
from pathlib import Path

from app.services.chroma_client import get_chroma_client, persist_client
from app.services.embedder import Embedder


class ChromaIngestor:
    _default_max_batch_size = 5000
    _allowed_collection_names = {"nx2meapp", "kinexushhd"}
    _app_aliases = {
        "nx2me": "Nx2meApp",
        "nx2meapp": "Nx2meApp",
        "kinexushhd": "kinexushhd",
    }

    def __init__(self):
        self.client = get_chroma_client()
        self.embedding = Embedder().get_embedding_function()

    def ingest_chunks(self, chunks):
        if not chunks:
            raise RuntimeError("No chunks were provided for ChromaDB ingestion.")

        self._clear_all_collections()
        app_name = self._normalize_app_name(chunks[0].get("app") or "app")
        self._ingest_collection(self._build_collection_name(app_name), chunks, replace=True)
        persist_client(self.client)

    def ingest_processed_directory(self, processed_dir):
        processed_path = Path(processed_dir)
        if not processed_path.exists():
            raise RuntimeError(f"Processed directory not found: {processed_path}")

        app_directories = sorted(path for path in processed_path.iterdir() if path.is_dir())
        if not app_directories:
            raise RuntimeError(f"No processed application folders were found in: {processed_path}")

        self._clear_all_collections()
        ingested_collections = []
        for app_dir in app_directories:
            chunks = self._load_app_chunks(app_dir)
            if not chunks:
                continue

            app_name = self._normalize_app_name(chunks[0].get("app") or app_dir.name)
            collection_name = self._build_collection_name(app_name)
            if collection_name not in self._allowed_collection_names:
                continue
            self._ingest_collection(collection_name, chunks, replace=True)
            ingested_collections.append(collection_name)

        persist_client(self.client)
        return ingested_collections

    def _clear_all_collections(self):
        try:
            collections = self.client.list_collections()
        except Exception:
            return

        for collection in collections:
            collection_name = collection if isinstance(collection, str) else getattr(collection, "name", "")
            if not collection_name:
                continue
            try:
                self.client.delete_collection(name=collection_name)
            except Exception:
                pass

    def _reset_collection(self, collection_name):
        try:
            self.client.delete_collection(name=collection_name)
        except Exception:
            pass

    def _ingest_collection(self, collection_name, chunks, replace):
        if replace:
            self._reset_collection(collection_name)

        collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding,
        )

        documents = []
        metadatas = []
        ids = []

        for index, chunk in enumerate(chunks):
            text = self._build_document_text(chunk).strip()
            if not text:
                continue

            documents.append(text)
            metadatas.append(self._build_metadata(chunk))
            ids.append(
                str(chunk.get("chunk_id") or chunk.get("id") or f"{collection_name}-chunk-{index}")
            )

        if not documents:
            return

        try:
            max_batch_size = self._get_max_batch_size(collection)
            for start in range(0, len(documents), max_batch_size):
                stop = start + max_batch_size
                collection.add(
                    documents=documents[start:stop],
                    metadatas=metadatas[start:stop],
                    ids=ids[start:stop],
                )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to ingest documents into ChromaDB collection '{collection_name}'."
            ) from exc

    def _get_max_batch_size(self, collection):
        try:
            max_batch_size = int(collection._client.get_max_batch_size())
            if max_batch_size > 0:
                return max_batch_size
        except Exception:
            pass

        return self._default_max_batch_size

    def _load_app_chunks(self, app_dir):
        chunks = []
        for jsonl_path in sorted(app_dir.glob("*_chunks.jsonl")):
            with open(jsonl_path, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    chunks.append(json.loads(line))
        return chunks

    def _build_metadata(self, chunk):
        metadata = {
            "app": self._normalize_app_name(chunk.get("app") or "unknown"),
            "domain": str(chunk.get("domain") or "general"),
            "type": str(chunk.get("type") or "text"),
            "section": str(chunk.get("section") or "general"),
        }

        if chunk.get("page") is not None:
            metadata["page"] = int(chunk["page"])

        if chunk.get("image_path") is not None:
            metadata["image_path"] = str(chunk["image_path"])

        keywords = chunk.get("keywords") or []
        if keywords:
            metadata["keywords"] = ", ".join(str(keyword) for keyword in keywords)

        return metadata

    def _build_document_text(self, chunk):
        text = (chunk.get("text") or "").strip()
        section = (chunk.get("section") or "").strip()
        domain = (chunk.get("domain") or "").strip()
        chunk_type = (chunk.get("type") or "").strip()
        keywords = chunk.get("keywords") or []
        image_path = (chunk.get("image_path") or "").strip()

        parts = [part for part in [section, text] if part]
        if domain:
            parts.append(f"Domain: {domain}")
        if chunk_type:
            parts.append(f"Type: {chunk_type}")
        if keywords:
            parts.append("Keywords: " + ", ".join(str(keyword) for keyword in keywords))
        if image_path:
            parts.append(f"Image path: {image_path}")

        return "\n\n".join(parts)

    def _build_collection_name(self, app_name):
        return self._slugify(app_name or "app")

    def _normalize_app_name(self, app_name):
        raw_name = str(app_name or "").strip()
        key = self._slugify(raw_name)
        return self._app_aliases.get(key, raw_name or "app")

    def _slugify(self, value):
        slug = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
        return slug or "app"
