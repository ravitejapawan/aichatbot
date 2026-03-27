import json
import threading
from collections import OrderedDict
import re

from app.config import ANSWER_CACHE_SIZE, DETAILED_TOP_K
from app.rag.prompt import PromptBuilder
from app.rag.retriever import Retriever
from app.services.llm import LLM


class RAGPipeline:
    _answer_cache = OrderedDict()
    _cache_lock = threading.Lock()
    _follow_up_prompt = (
        "Would you like a detailed walkthrough from the documents, "
        "or should I show reference images?"
    )
    _source_specific_detail_pattern = re.compile(
        r'^please provide a detailed walkthrough from the documents for\s+["“].+["”]\.?\s*$',
        flags=re.IGNORECASE,
    )
    _source_specific_visual_pattern = re.compile(
        r'^please show reference images for\s+["“].+["”]\.?\s*$',
        flags=re.IGNORECASE,
    )
    _generic_visual_pattern = re.compile(
        r"^please show reference images related to this answer\.?\s*$",
        flags=re.IGNORECASE,
    )
    _detailed_top_k = DETAILED_TOP_K
    _detailed_prompt_max_chunks = 5
    _detailed_chunk_char_limit = 900
    _detailed_num_predict = 520

    def __init__(self):
        self.retriever = Retriever()
        self.prompt_builder = PromptBuilder()
        self.llm = LLM()

    def warmup(self):
        self.retriever.warmup()
        self.llm.warmup()

    def run(self, query, history=None, where=None):
        history = history or []
        detailed_requested = self._query_requests_detailed(query)
        cache_key = self._build_cache_key(query, history, where)
        cached = self._get_cached_answer(cache_key)
        if cached is not None:
            return cached

        retrieval_query, route, chunks = self._prepare_retrieval(
            query,
            history,
            where,
            detailed=detailed_requested,
        )

        if not chunks:
            result = {
                "answer": "I could not find relevant information in the knowledge base.",
                "sources": [],
                "steps": [],
                "collection": route["collection"],
                "app": route["app"],
                "routing": route,
            }
            self._store_cached_answer(cache_key, result)
            return result

        if self._query_requests_visual(query):
            answer = self._build_chunk_fallback_answer(query, chunks)
            answer = self._append_follow_up_prompt(answer)
            result = {
                "answer": answer,
                "sources": chunks,
                "steps": [],
                "collection": route["collection"],
                "app": route["app"],
                "routing": route,
            }
            self._store_cached_answer(cache_key, result)
            return result

        prompt = self.prompt_builder.build(
            query,
            chunks,
            history=history,
            detailed=detailed_requested,
            max_chunks=self._detailed_prompt_max_chunks if detailed_requested else None,
            chunk_char_limit=self._detailed_chunk_char_limit if detailed_requested else None,
        )
        llm_options = {"num_predict": self._detailed_num_predict} if detailed_requested else None
        answer = self.llm.generate(prompt, options=llm_options)
        answer = self._finalize_answer(query, answer, chunks)
        result = {
            "answer": answer,
            "sources": chunks,
            "steps": [],
            "collection": route["collection"],
            "app": route["app"],
            "routing": route,
        }
        self._store_cached_answer(cache_key, result)
        return result

    def stream(self, query, history=None, where=None):
        history = history or []
        detailed_requested = self._query_requests_detailed(query)
        cache_key = self._build_cache_key(query, history, where)
        cached = self._get_cached_answer(cache_key)
        if cached is not None:
            yield {
                "type": "meta",
                "collection": cached["collection"],
                "app": cached["app"],
                "routing": cached["routing"],
                "sources": cached["sources"],
                "steps": [],
            }
            yield {"type": "token", "text": cached["answer"]}
            yield {"type": "done"}
            return

        retrieval_query, route, chunks = self._prepare_retrieval(
            query,
            history,
            where,
            detailed=detailed_requested,
        )

        if not chunks:
            result = {
                "answer": "I could not find this in the knowledge base. Please check with the L3 administration team.",
                "sources": [],
                "steps": [],
                "collection": route["collection"],
                "app": route["app"],
                "routing": route,
            }
            self._store_cached_answer(cache_key, result)
            yield {
                "type": "meta",
                "collection": route["collection"],
                "app": route["app"],
                "routing": route,
                "sources": [],
                "steps": [],
            }
            yield {
                "type": "token",
                "text": result["answer"],
            }
            yield {"type": "done"}
            return

        if self._query_requests_visual(query):
            answer = self._build_chunk_fallback_answer(query, chunks)
            answer = self._append_follow_up_prompt(answer)
            self._store_cached_answer(
                cache_key,
                {
                    "answer": answer,
                    "sources": chunks,
                    "steps": [],
                    "collection": route["collection"],
                    "app": route["app"],
                    "routing": route,
                },
            )
            yield {
                "type": "meta",
                "collection": route["collection"],
                "app": route["app"],
                "routing": route,
                "sources": chunks,
                "steps": [],
            }
            yield {"type": "token", "text": answer}
            yield {"type": "done"}
            return

        prompt = self.prompt_builder.build(
            query,
            chunks,
            history=history,
            detailed=detailed_requested,
            max_chunks=self._detailed_prompt_max_chunks if detailed_requested else None,
            chunk_char_limit=self._detailed_chunk_char_limit if detailed_requested else None,
        )
        llm_options = {"num_predict": self._detailed_num_predict} if detailed_requested else None
        yield {
            "type": "meta",
            "collection": route["collection"],
            "app": route["app"],
            "routing": route,
            "sources": chunks,
            "steps": [],
        }

        answer_parts = []
        for text in self.llm.stream_generate(prompt, options=llm_options):
            answer_parts.append(text)
            yield {"type": "token", "text": text}

        raw_answer = "".join(answer_parts)
        final_answer = self._finalize_answer(query, raw_answer, chunks)

        if final_answer.startswith(raw_answer):
            suffix = final_answer[len(raw_answer):]
            if suffix:
                yield {"type": "token", "text": suffix}
        elif final_answer != raw_answer:
            yield {"type": "token", "text": "\n\n" + self._follow_up_prompt}

        self._store_cached_answer(
            cache_key,
            {
                "answer": final_answer,
                "sources": chunks,
                "steps": [],
                "collection": route["collection"],
                "app": route["app"],
                "routing": route,
            },
        )
        yield {"type": "done"}

    def _prepare_retrieval(self, query, history, where, detailed=False):
        normalized_query = self._normalize_follow_up_query(query, detailed=detailed)
        retrieval_query = self._build_retrieval_query(
            normalized_query,
            history,
            visual=self._query_requests_visual(query),
        )
        top_k = self._detailed_top_k if detailed else None
        route, chunks = self.retriever.retrieve(
            retrieval_query,
            history=history,
            where=where,
            top_k=top_k,
        )
        return retrieval_query, route, chunks

    def _build_retrieval_query(self, query, history, visual=False):
        if visual:
            visual_query = self._build_visual_retrieval_query(query, history)
            if visual_query:
                return visual_query

        recent_user_turns = []

        for turn in history[-6:]:
            role = (turn.get("role") or "").strip().lower()
            text = (turn.get("text") or "").strip()
            if role == "user" and text:
                recent_user_turns.append(text)

        if not recent_user_turns:
            return query

        recent_context = " ".join(recent_user_turns[-3:])
        return f"{recent_context}\n{query}".strip()

    def _build_visual_retrieval_query(self, query, history):
        latest_user = self._latest_turn_text(history, "user")
        latest_assistant = self._latest_turn_text(history, "assistant")
        section, page = self._extract_recent_section_and_page(latest_assistant)

        parts = []
        if latest_user:
            parts.append(latest_user)
        if section:
            parts.append(f"Section: {section}")
        if page:
            parts.append(f"Page: {page}")

        assistant_summary = self._summarize_assistant_context(latest_assistant)
        if assistant_summary:
            parts.append(f"Previous answer context: {assistant_summary}")

        if section:
            parts.append(f'Please show reference images for "{section}".')
        else:
            parts.append(query)

        parts.append("Prefer the same screen, screenshot, or UI panel from the referenced section.")
        return "\n".join(part for part in parts if part).strip()

    def _normalize_follow_up_query(self, query, detailed=False):
        normalized_query = str(query or "").strip()
        if self._source_specific_detail_pattern.match(normalized_query):
            return "Please provide a detailed walkthrough from the documents."

        if self._source_specific_visual_pattern.match(normalized_query):
            return normalized_query

        if self._generic_visual_pattern.match(normalized_query):
            return "Please show reference images related to this answer."

        if not detailed:
            return normalized_query

        return normalized_query

    def _latest_turn_text(self, history, role):
        target_role = str(role or "").strip().lower()
        for turn in reversed(history or []):
            if str(turn.get("role") or "").strip().lower() != target_role:
                continue
            text = str(turn.get("text") or "").strip()
            if text:
                return text
        return ""

    def _extract_recent_section_and_page(self, text):
        raw = str(text or "").strip()
        if not raw:
            return "", None

        compact = re.sub(r"\s+", " ", raw)
        match = re.search(
            r"most relevant section is\s+\*{0,2}(.+?)\*{0,2}(?:\s+on page\s+(\d+))?(?:[.\n]|$)",
            compact,
            flags=re.IGNORECASE,
        )
        if not match:
            return "", None

        section = re.sub(r"^\W+|\W+$", "", match.group(1) or "").strip()
        page_text = match.group(2)
        try:
            page = int(page_text) if page_text else None
        except ValueError:
            page = None
        return section, page

    def _summarize_assistant_context(self, text):
        cleaned = self._clean_fallback_text(text)
        cleaned = re.sub(r"would you like a detailed walkthrough.*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip()
        if not cleaned:
            return ""
        return cleaned[:360].rstrip()

    def _build_cache_key(self, query, history, where):
        history_text = " || ".join(
            f"{(turn.get('role') or '').strip().lower()}:{self._normalize_text(turn.get('text') or '')}"
            for turn in history[-4:]
            if (turn.get("text") or "").strip()
        )
        where_text = json.dumps(where or {}, sort_keys=True, ensure_ascii=False)
        return f"{self._normalize_text(query)}::{history_text}::{where_text}"

    def _normalize_text(self, value):
        return " ".join(str(value or "").strip().lower().split())

    def _get_cached_answer(self, key):
        cache = self.__class__._answer_cache
        with self.__class__._cache_lock:
            if key not in cache:
                return None
            value = cache.pop(key)
            cache[key] = value
            return dict(value) if isinstance(value, dict) else value

    def _store_cached_answer(self, key, value):
        cache = self.__class__._answer_cache
        with self.__class__._cache_lock:
            if key in cache:
                cache.pop(key)
            cache[key] = dict(value) if isinstance(value, dict) else value
            while len(cache) > ANSWER_CACHE_SIZE:
                cache.popitem(last=False)

    def _finalize_answer(self, query, answer, chunks):
        normalized = self._normalize_text(answer)
        if chunks and (
            "could not find this in the knowledge base" in normalized
            or "please check with the l3 administration team" in normalized
        ):
            return self._build_chunk_fallback_answer(query, chunks)

        return self._append_follow_up_prompt(answer)

    def _build_chunk_fallback_answer(self, query, chunks):
        primary = chunks[0]
        section = primary.get("section") or "Relevant section"
        page = primary.get("page")
        text = self._clean_fallback_text(primary.get("text") or "")

        if self._query_requests_visual(query) and page:
            lead = f"- The most relevant section is **{section}** on page {page}."
        elif page:
            lead = f"- The most relevant section is **{section}** on page {page}."
        else:
            lead = f"- The most relevant section is **{section}**."

        details = text[:520].strip()
        if len(text) > 520:
            details = details.rstrip() + "..."

        if not details:
            return lead

        return f"{lead}\n- {details}"

    def _clean_fallback_text(self, text):
        cleaned = str(text or "").strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        cleaned = re.sub(r"\bFigure\s+\d+(?:[-.]\d+)?\s*\([A-Z]\)", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bsee the [^.]+\.", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(
            r"\bDomain:\s.*?(?=\b(?:Type|Keywords|Image path):|$)",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"\bType:\s.*?(?=\b(?:Keywords|Image path):|$)",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"\bKeywords:\s.*?(?=\bImage path:|$)",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\bImage path:\s.*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        return cleaned.strip(" .")

    def _query_requests_visual(self, query):
        normalized = self._normalize_text(query)
        return any(term in normalized for term in ("figure", "show", "image", "screenshot", "card"))

    def _query_requests_detailed(self, query):
        normalized = self._normalize_text(query)
        detailed_terms = (
            "detailed",
            "detail",
            "walkthrough",
            "step by step",
            "step-by-step",
            "in detail",
            "all information",
            "all details",
            "from the documents",
        )
        return any(term in normalized for term in detailed_terms)

    def _append_follow_up_prompt(self, answer):
        cleaned = str(answer or "").strip()
        if not cleaned:
            return cleaned

        normalized = self._normalize_text(cleaned)
        if "detailed walkthrough" in normalized and "reference images" in normalized:
            return cleaned

        return f"{cleaned}\n\n{self._follow_up_prompt}"
