from __future__ import annotations

import hashlib
import json
import math
import urllib.error
import urllib.request
from typing import Any, Dict, Iterable, List, Optional

from .config import MempalaceConfig


class PalaceStore:
    def __init__(self, config: Optional[MempalaceConfig] = None) -> None:
        self.config = config or MempalaceConfig()

    @property
    def qdrant_url(self) -> str:
        return self.config.qdrant_url.rstrip("/")

    def _request(self, method: str, path: str, payload: Optional[dict] = None) -> dict:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.qdrant_url}{path}",
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.config.request_timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Qdrant request failed ({method} {path}): {detail}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Qdrant unavailable at {self.qdrant_url}: {e}") from e

        if not raw:
            return {}
        return json.loads(raw)

    def _ollama_request(self, payload: dict) -> dict:
        base_url = self.config.ollama_url.rstrip("/")
        req = urllib.request.Request(
            f"{base_url}/api/embeddings",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.config.request_timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ollama embedding request failed: {detail}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Ollama unavailable at {base_url}: {e}") from e
        return json.loads(raw)

    def ensure_collection(self, collection_name: Optional[str] = None) -> None:
        name = collection_name or self.config.collection_name
        try:
            payload = self._request("GET", f"/collections/{name}")
            if payload.get("status") == "ok":
                return
        except RuntimeError as e:
            if "doesn't exist" not in str(e) and "Not found" not in str(e):
                raise
        self._request(
            "PUT",
            f"/collections/{name}",
            {
                "vectors": {
                    "size": int(self.config.embedding_dimension),
                    "distance": str(self.config.qdrant_distance),
                }
            },
        )

    def embed_text(self, text: str) -> List[float]:
        result = self._ollama_request({"model": self.config.embedding_model, "prompt": text})
        embedding = result.get("embedding")
        if not isinstance(embedding, list):
            raise RuntimeError("Ollama response did not include an embedding vector")
        if len(embedding) != int(self.config.embedding_dimension):
            raise RuntimeError(
                f"Embedding dimension mismatch: expected {self.config.embedding_dimension}, got {len(embedding)}"
            )
        return [float(x) for x in embedding]

    def _match_filter(self, key: str, value: str) -> dict:
        return {"key": key, "match": {"value": value}}

    def _build_filter(
        self,
        wing: Optional[str] = None,
        room: Optional[str] = None,
        source_file: Optional[str] = None,
        drawer_id: Optional[str] = None,
    ) -> Optional[dict]:
        must = []
        if wing:
            must.append(self._match_filter("wing", wing))
        if room:
            must.append(self._match_filter("room", room))
        if source_file:
            must.append(self._match_filter("source_file", source_file))
        if drawer_id:
            must.append(self._match_filter("drawer_id", drawer_id))
        return {"must": must} if must else None

    def _point_id(self, drawer_id: str) -> str:
        digest = hashlib.md5(drawer_id.encode("utf-8")).hexdigest()
        return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"

    def _point_payload(self, drawer_id: str, text: str, metadata: dict) -> dict:
        payload = dict(metadata)
        payload["drawer_id"] = drawer_id
        payload["text"] = text
        return payload

    def _point_to_record(self, point: dict) -> dict:
        payload = point.get("payload") or {}
        text = payload.get("text", "")
        metadata = dict(payload)
        metadata.pop("text", None)
        return {
            "id": payload.get("drawer_id") or point.get("id"),
            "text": text,
            "metadata": metadata,
            "score": point.get("score"),
        }

    def upsert_drawer(
        self,
        drawer_id: str,
        text: str,
        metadata: dict,
        collection_name: Optional[str] = None,
    ) -> dict:
        name = collection_name or self.config.collection_name
        self.ensure_collection(name)
        vector = self.embed_text(text)
        payload = self._point_payload(drawer_id, text, metadata)
        return self._request(
            "PUT",
            f"/collections/{name}/points",
            {
                "points": [
                    {
                        "id": self._point_id(drawer_id),
                        "vector": vector,
                        "payload": payload,
                    }
                ]
            },
        )

    def delete_drawer(self, drawer_id: str, collection_name: Optional[str] = None) -> dict:
        name = collection_name or self.config.collection_name
        self.ensure_collection(name)
        return self._request(
            "POST",
            f"/collections/{name}/points/delete",
            {"filter": self._build_filter(drawer_id=drawer_id)},
        )

    def search(
        self,
        query: str,
        wing: Optional[str] = None,
        room: Optional[str] = None,
        n_results: int = 5,
        collection_name: Optional[str] = None,
    ) -> List[dict]:
        name = collection_name or self.config.collection_name
        self.ensure_collection(name)
        vector = self.embed_text(query)
        payload = {
            "vector": vector,
            "limit": n_results,
            "with_payload": True,
            "with_vector": False,
        }
        query_filter = self._build_filter(wing=wing, room=room)
        if query_filter:
            payload["filter"] = query_filter
        results = self._request("POST", f"/collections/{name}/points/search", payload)
        hits = []
        for point in results.get("result", []):
            record = self._point_to_record(point)
            score = float(record.get("score") or 0.0)
            record["similarity"] = round(score, 3) if not math.isnan(score) else 0.0
            hits.append(record)
        return hits

    def scroll(
        self,
        wing: Optional[str] = None,
        room: Optional[str] = None,
        source_file: Optional[str] = None,
        limit: int = 100,
        collection_name: Optional[str] = None,
    ) -> List[dict]:
        name = collection_name or self.config.collection_name
        self.ensure_collection(name)
        payload = {
            "limit": limit,
            "with_payload": True,
            "with_vector": False,
        }
        query_filter = self._build_filter(wing=wing, room=room, source_file=source_file)
        if query_filter:
            payload["filter"] = query_filter
        results = self._request("POST", f"/collections/{name}/points/scroll", payload)
        return [self._point_to_record(point) for point in results.get("result", {}).get("points", [])]

    def get_by_source_file(
        self,
        source_file: str,
        limit: int = 1,
        collection_name: Optional[str] = None,
    ) -> List[dict]:
        return self.scroll(source_file=source_file, limit=limit, collection_name=collection_name)

    def get_by_ids(self, ids: Iterable[str], collection_name: Optional[str] = None) -> List[dict]:
        wanted = list(ids)
        if not wanted:
            return []
        name = collection_name or self.config.collection_name
        self.ensure_collection(name)
        payload = {
            "limit": max(len(wanted), 1),
            "with_payload": True,
            "with_vector": False,
            "filter": {"should": [self._match_filter("drawer_id", drawer_id) for drawer_id in wanted]},
        }
        results = self._request("POST", f"/collections/{name}/points/scroll", payload)
        found = [self._point_to_record(point) for point in results.get("result", {}).get("points", [])]
        order = {drawer_id: i for i, drawer_id in enumerate(wanted)}
        found.sort(key=lambda item: order.get(item["id"], len(wanted)))
        return found

    def count(
        self,
        wing: Optional[str] = None,
        room: Optional[str] = None,
        collection_name: Optional[str] = None,
    ) -> int:
        name = collection_name or self.config.collection_name
        self.ensure_collection(name)
        payload = {"exact": True}
        query_filter = self._build_filter(wing=wing, room=room)
        if query_filter:
            payload["filter"] = query_filter
        results = self._request("POST", f"/collections/{name}/points/count", payload)
        return int(results.get("result", {}).get("count", 0))


class QdrantCollectionAdapter:
    def __init__(self, store: PalaceStore, collection_name: Optional[str] = None) -> None:
        self.store = store
        self.collection_name = collection_name or store.config.collection_name
        self.store.ensure_collection(self.collection_name)

    def add(self, documents: List[str], ids: List[str], metadatas: List[dict]) -> Any:
        for drawer_id, text, metadata in zip(ids, documents, metadatas):
            if self.get(ids=[drawer_id]).get("ids"):
                raise RuntimeError(f"Drawer already exists: {drawer_id}")
            self.store.upsert_drawer(drawer_id, text, metadata, self.collection_name)
        return {"ids": ids}

    def upsert(self, ids: List[str], documents: List[str], metadatas: List[dict]) -> Any:
        for drawer_id, text, metadata in zip(ids, documents, metadatas):
            self.store.upsert_drawer(drawer_id, text, metadata, self.collection_name)
        return {"ids": ids}

    def count(self) -> int:
        return self.store.count(collection_name=self.collection_name)

    def get(
        self,
        where: Optional[dict] = None,
        ids: Optional[List[str]] = None,
        limit: Optional[int] = None,
        include: Optional[List[str]] = None,
        offset: int = 0,
    ) -> dict:
        include = include or []
        if ids:
            records = self.store.get_by_ids(ids, collection_name=self.collection_name)
        else:
            wing = _extract_match(where, "wing") if where else None
            room = _extract_match(where, "room") if where else None
            source_file = _extract_match(where, "source_file") if where else None
            records = self.store.scroll(
                wing=wing,
                room=room,
                source_file=source_file,
                limit=(limit or 10000) + offset,
                collection_name=self.collection_name,
            )
            if offset:
                records = records[offset:]
            if limit is not None:
                records = records[:limit]

        return {
            "ids": [record["id"] for record in records],
            "documents": [record["text"] for record in records] if "documents" in include else [],
            "metadatas": [record["metadata"] for record in records] if "metadatas" in include else [],
        }

    def query(
        self,
        query_texts: List[str],
        n_results: int = 5,
        where: Optional[dict] = None,
        include: Optional[List[str]] = None,
    ) -> dict:
        include = include or []
        all_ids = []
        all_documents = []
        all_metadatas = []
        all_distances = []

        wing = _extract_match(where, "wing") if where else None
        room = _extract_match(where, "room") if where else None

        for query in query_texts:
            hits = self.store.search(
                query=query,
                wing=wing,
                room=room,
                n_results=n_results,
                collection_name=self.collection_name,
            )
            all_ids.append([hit["id"] for hit in hits])
            all_documents.append([hit["text"] for hit in hits] if "documents" in include else [])
            all_metadatas.append([hit["metadata"] for hit in hits] if "metadatas" in include else [])
            all_distances.append(
                [max(0.0, 1.0 - float(hit.get("similarity", 0.0))) for hit in hits]
                if "distances" in include
                else []
            )

        return {
            "ids": all_ids,
            "documents": all_documents,
            "metadatas": all_metadatas,
            "distances": all_distances,
        }

    def delete(self, ids: List[str]) -> Any:
        for drawer_id in ids:
            self.store.delete_drawer(drawer_id, self.collection_name)
        return {"ids": ids}


class QdrantClientAdapter:
    def __init__(self, config: Optional[MempalaceConfig] = None) -> None:
        self.config = config or MempalaceConfig()
        self.store = PalaceStore(self.config)

    def get_collection(self, name: str) -> Any:
        self.store.ensure_collection(name)
        return QdrantCollectionAdapter(self.store, name)

    def create_collection(self, name: str) -> Any:
        self.store.ensure_collection(name)
        return QdrantCollectionAdapter(self.store, name)

    def get_or_create_collection(self, name: str) -> Any:
        self.store.ensure_collection(name)
        return QdrantCollectionAdapter(self.store, name)


def get_store(config: Optional[MempalaceConfig] = None) -> PalaceStore:
    return PalaceStore(config or MempalaceConfig())


def _extract_match(where: Optional[dict], key: str) -> Optional[str]:
    if not where:
        return None
    if key in where:
        return where[key]
    if "$and" in where:
        for clause in where["$and"]:
            if key in clause:
                return clause[key]
    return None
