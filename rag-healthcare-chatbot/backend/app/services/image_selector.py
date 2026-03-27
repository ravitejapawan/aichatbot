import json
import mimetypes
import re
import threading
from collections import OrderedDict
from pathlib import Path

import fitz

from app.config import (
    IMAGE_SELECTOR_CANDIDATE_WINDOW,
    IMAGE_SELECTOR_MAX_MODEL_CANDIDATES,
    IMAGE_SELECTOR_MIN_PDF_IMAGE_HEIGHT,
    IMAGE_SELECTOR_MIN_PDF_IMAGE_WIDTH,
    IMAGE_SELECTOR_PDF_PAGE_WINDOW,
    PROCESSED_DATA_DIR,
)
from app.services.llm import LLM


class KnowledgeImageSelector:
    _chunk_cache = {}
    _selection_cache = OrderedDict()
    _cache_lock = threading.Lock()
    _cache_size = 128
    _candidate_window = IMAGE_SELECTOR_CANDIDATE_WINDOW
    _pdf_page_window = IMAGE_SELECTOR_PDF_PAGE_WINDOW
    _max_model_candidates = IMAGE_SELECTOR_MAX_MODEL_CANDIDATES
    _min_pdf_image_width = IMAGE_SELECTOR_MIN_PDF_IMAGE_WIDTH
    _min_pdf_image_height = IMAGE_SELECTOR_MIN_PDF_IMAGE_HEIGHT

    def __init__(self, processed_dir=None, llm=None):
        self.processed_dir = Path(processed_dir or PROCESSED_DATA_DIR)
        self.llm = llm or LLM()

    def select_figure(self, collection, pdf_path, page, section="", context="", use_model=True):
        cache_key = self._build_cache_key(
            collection,
            page,
            section,
            mode="figure",
            context=context,
        )
        cached = self._get_cached_selection(cache_key)
        if cached is not None:
            return dict(cached)

        pdf_candidates = self._collect_pdf_candidates(
            pdf_path=pdf_path,
            page=page,
            section=section,
            context=context,
        )
        if not pdf_candidates:
            return None

        shortlist = pdf_candidates[: self._max_model_candidates]
        selected = None
        if use_model:
            selected = self._select_pdf_candidate_with_model(
                collection=collection,
                page=page,
                section=section,
                context=context,
                candidates=shortlist,
            )
        chosen = selected or shortlist[0]
        result = self._build_pdf_selection_result(chosen)
        if result is not None:
            self._store_cached_selection(cache_key, result)
        return result

    def select_image(self, collection, page, section="", use_model=True):
        cache_key = self._build_cache_key(collection, page, section, mode="image")
        cached = self._get_cached_selection(cache_key)
        if cached is not None:
            return dict(cached)

        candidates = self._collect_candidates(collection, page, section)
        if not candidates:
            return None

        shortlist = candidates[: self._max_model_candidates]
        selected = None
        if use_model:
            selected = self._select_with_model(
                collection=collection,
                page=page,
                section=section,
                candidates=shortlist,
            )
        chosen = selected or shortlist[0]
        result = self._build_selection_result(chosen)
        if result is not None:
            self._store_cached_selection(cache_key, result)
        return result

    def _collect_pdf_candidates(self, pdf_path, page, section, context):
        path = Path(pdf_path)
        if not path.exists():
            return []

        requested_page = int(page)
        scored = []
        seen = set()

        with fitz.open(path) as document:
            for candidate_page in self._candidate_pages(requested_page, len(document)):
                pdf_page = document.load_page(candidate_page - 1)
                anchor = self._find_best_anchor(pdf_page, section=section, context=context)
                image_rects = self._image_rects_from_page(pdf_page)
                if not image_rects:
                    continue

                for rect in image_rects:
                    rect_key = (
                        candidate_page,
                        round(rect.x0, 1),
                        round(rect.y0, 1),
                        round(rect.x1, 1),
                        round(rect.y1, 1),
                    )
                    if rect_key in seen:
                        continue
                    seen.add(rect_key)

                    nearby_text = self._extract_nearby_text(pdf_page, rect)
                    score = self._score_pdf_candidate(
                        requested_page=requested_page,
                        candidate_page=candidate_page,
                        section=section,
                        context=context,
                        nearby_text=nearby_text,
                        rect=rect,
                        anchor=anchor,
                    )
                    if score <= 0:
                        continue

                    scored.append(
                        {
                            "page": candidate_page,
                            "section": str(section or ""),
                            "context": self._compact_text(context or "", limit=220),
                            "nearby_text": self._compact_text(nearby_text, limit=320),
                            "clip_rect": self._expand_rect(pdf_page, rect),
                            "score": score,
                            "width": round(rect.width, 1),
                            "height": round(rect.height, 1),
                        }
                    )

        scored.sort(
            key=lambda item: (
                -item["score"],
                abs(item["page"] - requested_page),
                -(item["width"] * item["height"]),
            )
        )
        return scored

    def _collect_candidates(self, collection, page, section):
        chunks = self._load_processed_chunks(collection)
        if not chunks:
            return []

        scored = []
        seen_paths = set()
        for chunk in chunks:
            raw_path = str(chunk.get("image_path") or "").strip()
            if not raw_path:
                continue

            resolved_path = self._resolve_image_path(collection, raw_path)
            if resolved_path is None or resolved_path in seen_paths:
                continue

            candidate_page = self._safe_int(chunk.get("page"))
            if candidate_page is None or abs(candidate_page - int(page)) > self._candidate_window:
                continue

            score = self._score_candidate(
                page=page,
                section=section,
                candidate_page=candidate_page,
                candidate_section=str(chunk.get("section") or ""),
                candidate_text=str(chunk.get("text") or ""),
            )
            if score <= 0:
                continue

            seen_paths.add(resolved_path)
            scored.append(
                {
                    "page": candidate_page,
                    "section": str(chunk.get("section") or ""),
                    "text": self._compact_text(chunk.get("text") or "", limit=280),
                    "domain": str(chunk.get("domain") or ""),
                    "image_path": resolved_path,
                    "relative_path": self._relative_image_path(resolved_path),
                    "score": score,
                }
            )

        scored.sort(
            key=lambda item: (
                -item["score"],
                abs(item["page"] - int(page)),
                item["section"].lower(),
            )
        )
        return scored

    def _select_with_model(self, collection, page, section, candidates):
        if len(candidates) <= 1:
            return candidates[0] if candidates else None

        prompt = self._build_selection_prompt(collection, page, section, candidates)
        try:
            raw = self.llm.generate(prompt, options={"num_predict": 80, "temperature": 0})
        except RuntimeError:
            return None

        parsed = self._parse_selection(raw)
        choice = parsed.get("choice")
        if not isinstance(choice, int):
            return None
        if choice < 1 or choice > len(candidates):
            return None
        return candidates[choice - 1]

    def _select_pdf_candidate_with_model(self, collection, page, section, context, candidates):
        if len(candidates) <= 1:
            return candidates[0] if candidates else None

        prompt = self._build_pdf_selection_prompt(collection, page, section, context, candidates)
        try:
            raw = self.llm.generate(prompt, options={"num_predict": 120, "temperature": 0})
        except RuntimeError:
            return None

        parsed = self._parse_selection(raw)
        choice = parsed.get("choice")
        if not isinstance(choice, int):
            return None
        if choice < 1 or choice > len(candidates):
            return None
        return candidates[choice - 1]

    def _build_selection_prompt(self, collection, page, section, candidates):
        lines = []
        for index, candidate in enumerate(candidates, start=1):
            lines.append(
                f"[{index}] page={candidate['page']} | section={candidate['section'] or 'General'} | "
                f"domain={candidate['domain'] or 'general'} | rel_path={candidate['relative_path']}\n"
                f"context={candidate['text'] or 'No extracted context available.'}"
            )

        return f"""
You are choosing the best reference image for a healthcare support UI.

Pick the single candidate that most likely shows the requested screen or section.
Prefer:
- a direct match for the requested section
- the same page first, then nearby pages if they look more relevant
- fuller screenshots or panels over logos, small icons, or decorative graphics

Return strict JSON only:
{{
  "choice": 1,
  "reason": "short reason"
}}

If no candidate is suitable, return:
{{
  "choice": 0,
  "reason": "short reason"
}}

Requested collection: {collection}
Requested page: {page}
Requested section: {section or "Unknown"}

Candidates:
{chr(10).join(lines)}
""".strip()

    def _build_pdf_selection_prompt(self, collection, page, section, context, candidates):
        lines = []
        for index, candidate in enumerate(candidates, start=1):
            lines.append(
                f"[{index}] page={candidate['page']} | size={candidate['width']}x{candidate['height']} | "
                f"score={round(candidate['score'], 2)}\n"
                f"nearby_text={candidate['nearby_text'] or 'No nearby text found.'}"
            )

        return f"""
You are choosing the most relevant PDF figure region for a healthcare support UI.

Pick the single candidate that most likely contains the screenshot, panel, chart, or figure
the user needs for the requested page and context.

Prefer:
- same page first when relevance looks similar
- nearby text that matches the requested section or current context
- full UI screenshots or clear figures instead of tiny logos or decorative assets

Return strict JSON only:
{{
  "choice": 1,
  "reason": "short reason"
}}

If no candidate is suitable, return:
{{
  "choice": 0,
  "reason": "short reason"
}}

Requested collection: {collection}
Requested page: {page}
Requested section: {section or "Unknown"}
Current context: {self._compact_text(context or "", limit=280) or "Not provided"}

Candidates:
{chr(10).join(lines)}
""".strip()

    def _parse_selection(self, text):
        raw = str(text or "").strip()
        if not raw:
            return {}

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
            if not match:
                return {}
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return {}

    def _score_candidate(self, page, section, candidate_page, candidate_section, candidate_text):
        score = 0
        distance = abs(int(page) - int(candidate_page))
        if distance == 0:
            score += 24
        elif distance == 1:
            score += 16
        elif distance == 2:
            score += 8

        requested_section = self._normalize_text(section)
        section_text = self._normalize_text(candidate_section)
        candidate_body = self._normalize_text(candidate_text)

        if requested_section:
            if requested_section == section_text:
                score += 30
            requested_tokens = self._tokens(section)
            overlap = requested_tokens.intersection(self._tokens(candidate_section))
            score += len(overlap) * 8
            for token in requested_tokens:
                if token in candidate_body:
                    score += 3
        else:
            score += 2

        if candidate_body:
            if any(term in candidate_body for term in ("dashboard", "tab", "overview", "patient")):
                score += 2
            if any(term in candidate_body for term in ("logo", "copyright", "proprietary")):
                score -= 8

        return score

    def _score_pdf_candidate(self, requested_page, candidate_page, section, context, nearby_text, rect, anchor):
        score = 0.0
        distance = abs(int(requested_page) - int(candidate_page))
        if distance == 0:
            score += 28.0
        elif distance == 1:
            score += 18.0
        elif distance == 2:
            score += 10.0

        requested_tokens = self._tokens(f"{section} {context}")
        nearby_tokens = self._tokens(nearby_text)
        overlap = requested_tokens.intersection(nearby_tokens)
        score += float(len(overlap) * 10)

        normalized_nearby = self._normalize_text(nearby_text)
        if normalized_nearby:
            if any(term in normalized_nearby for term in ("dashboard", "patient", "therapy", "clinic", "overview")):
                score += 2.5
            if any(term in normalized_nearby for term in ("logo", "copyright", "confidential", "proprietary")):
                score -= 10.0

        area_score = min((rect.width * rect.height) / 12000.0, 18.0)
        score += area_score

        if anchor is not None:
            vertical_distance = abs(rect.y0 - anchor.y1)
            if rect.y0 >= anchor.y1 - 20:
                score += 4.0
            score -= vertical_distance / 1400.0

        if requested_tokens and not overlap:
            score -= 6.0

        return score

    def _build_selection_result(self, candidate):
        image_path = Path(candidate["image_path"])
        if not image_path.exists():
            return None

        media_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
        return {
            "image_path": str(image_path),
            "media_type": media_type,
            "page": candidate["page"],
            "section": candidate["section"],
        }

    def _build_pdf_selection_result(self, candidate):
        clip_rect = candidate.get("clip_rect")
        if not clip_rect:
            return None

        return {
            "mode": "pdf_region",
            "page": int(candidate["page"]),
            "section": candidate.get("section", ""),
            "clip_rect": [float(value) for value in clip_rect],
        }

    def _load_processed_chunks(self, collection):
        cache = self.__class__._chunk_cache
        if collection in cache:
            return cache[collection]

        app_dir = self.processed_dir / collection
        chunks = []
        if app_dir.exists():
            for jsonl_path in sorted(app_dir.glob("*_chunks.jsonl")):
                with open(jsonl_path, "r", encoding="utf-8") as handle:
                    for line in handle:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            chunks.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue

        cache[collection] = chunks
        return chunks

    def _resolve_image_path(self, collection, raw_path):
        path = Path(str(raw_path or "").strip())
        if not str(path):
            return None

        if path.is_absolute() and path.exists():
            return str(path)

        normalized = str(raw_path).replace("\\", "/").strip().lstrip("/")
        candidates = [
            self.processed_dir / normalized,
            self.processed_dir / collection / normalized,
            self.processed_dir / collection / "images" / Path(normalized).name,
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return None

    def _relative_image_path(self, image_path):
        try:
            return str(Path(image_path).resolve().relative_to(self.processed_dir.resolve())).replace("\\", "/")
        except ValueError:
            return Path(image_path).name

    def _build_cache_key(self, collection, page, section, mode="image", context=""):
        return (
            f"{mode}::{self._normalize_text(collection)}::{int(page)}::"
            f"{self._normalize_text(section)}::{self._normalize_text(context)}"
        )

    def _get_cached_selection(self, key):
        cache = self.__class__._selection_cache
        with self.__class__._cache_lock:
            if key not in cache:
                return None
            value = cache.pop(key)
            cache[key] = value
            return dict(value)

    def _store_cached_selection(self, key, value):
        cache = self.__class__._selection_cache
        with self.__class__._cache_lock:
            if key in cache:
                cache.pop(key)
            cache[key] = dict(value)
            while len(cache) > self.__class__._cache_size:
                cache.popitem(last=False)

    def _compact_text(self, text, limit):
        normalized = re.sub(r"\s+", " ", str(text or "").strip())
        if len(normalized) <= limit:
            return normalized
        return normalized[: limit - 3].rstrip() + "..."

    def _candidate_pages(self, requested_page, total_pages):
        ordered = []
        for offset in range(0, self._pdf_page_window + 1):
            for candidate in (requested_page + offset, requested_page - offset):
                if 1 <= candidate <= total_pages and candidate not in ordered:
                    ordered.append(candidate)
        return ordered

    def _image_rects_from_page(self, pdf_page):
        rects = []
        for image in pdf_page.get_images(full=True):
            xref = image[0]
            try:
                rects.extend(pdf_page.get_image_rects(xref))
            except Exception:
                continue

        filtered = []
        seen = set()
        for rect in rects:
            if rect.width < self._min_pdf_image_width or rect.height < self._min_pdf_image_height:
                continue
            key = (
                round(rect.x0, 1),
                round(rect.y0, 1),
                round(rect.x1, 1),
                round(rect.y1, 1),
            )
            if key in seen:
                continue
            seen.add(key)
            filtered.append(rect)
        return filtered

    def _find_best_anchor(self, pdf_page, section, context):
        for query in (section, f"{section} {context}".strip(), context):
            anchor = self._find_section_anchor(pdf_page, query)
            if anchor is not None:
                return anchor
        return None

    def _find_section_anchor(self, pdf_page, query):
        for term in self._search_terms(query):
            rects = pdf_page.search_for(term)
            if rects:
                return min(rects, key=lambda rect: rect.y0)

        tokens = list(self._tokens(query))
        if not tokens:
            return None

        best_rect = None
        best_score = 0
        for block in pdf_page.get_text("blocks"):
            x0, y0, x1, y1, text, *_ = block
            normalized = self._normalize_text(text)
            score = sum(1 for token in tokens if token in normalized)
            if score > best_score:
                best_score = score
                best_rect = fitz.Rect(x0, y0, x1, y1)

        return best_rect if best_score >= min(2, len(tokens)) else None

    def _search_terms(self, value):
        cleaned = str(value or "").strip()
        if not cleaned:
            return []

        variants = {
            cleaned,
            cleaned.replace("â€“", "-"),
            cleaned.replace("&", "and"),
            cleaned.replace("â€“", "-").replace("&", "and"),
        }
        return [term for term in variants if term]

    def _extract_nearby_text(self, pdf_page, rect):
        expanded = fitz.Rect(
            rect.x0 - 24,
            rect.y0 - 130,
            rect.x1 + 24,
            rect.y1 + 130,
        ) & pdf_page.rect
        parts = []
        for block in pdf_page.get_text("blocks", clip=expanded):
            text = str(block[4] or "").strip()
            if text:
                parts.append(text)
        return " ".join(parts)

    def _expand_rect(self, pdf_page, rect):
        expanded = (rect + (-12, -12, 12, 12)) & pdf_page.rect
        return (
            round(expanded.x0, 2),
            round(expanded.y0, 2),
            round(expanded.x1, 2),
            round(expanded.y1, 2),
        )

    def _normalize_text(self, value):
        return re.sub(r"\s+", " ", str(value or "").strip().lower())

    def _tokens(self, value):
        return {
            token
            for token in re.findall(r"[a-z0-9]+", self._normalize_text(value))
            if len(token) > 2
        }

    def _safe_int(self, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
