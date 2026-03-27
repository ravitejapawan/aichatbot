import json
import re
from functools import lru_cache
from contextlib import asynccontextmanager
from pathlib import Path

import fitz
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Response
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import PROCESSED_DATA_DIR, RAW_DATA_DIR
from app.models.feedback import FeedbackRequest
from app.models.request import ChatRequest
from app.rag.pipeline import RAGPipeline
from app.services.chroma_admin import (
    get_collection_overview,
    get_collection_preview,
    get_collection_records,
    list_collections,
)
from app.services.feedback_store import FeedbackStore
from app.services.image_selector import KnowledgeImageSelector


def _warm_local_services():
    rag.warmup()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _warm_local_services()
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
  allow_origins=[
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://localhost:3002",
    "http://127.0.0.1:3002",
  ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount(
  "/kb-images",
  StaticFiles(directory=str(Path(PROCESSED_DATA_DIR)), check_dir=False),
  name="kb-images",
)

rag = RAGPipeline()
feedback_store = FeedbackStore()
image_selector = KnowledgeImageSelector()


def _slugify(value: str) -> str:
  return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


@lru_cache(maxsize=1)
def _raw_pdf_lookup():
  raw_dir = Path(RAW_DATA_DIR)
  lookup = {}
  if not raw_dir.exists():
    return lookup

  for pdf_path in raw_dir.glob("*.pdf"):
    lookup[_slugify(pdf_path.stem)] = pdf_path
  return lookup


def _resolve_pdf_for_collection(collection: str):
  key = _slugify(collection)
  if not key:
    return None

  for stem_key, pdf_path in _raw_pdf_lookup().items():
    if key in stem_key or stem_key in key:
      return pdf_path
  return None


def _section_search_terms(section: str):
  cleaned = str(section or "").strip()
  if not cleaned:
    return []

  variants = {
    cleaned,
    cleaned.replace("–", "-"),
    cleaned.replace("&", "and"),
    cleaned.replace("–", "-").replace("&", "and"),
  }
  return [value for value in variants if value]


def _find_section_anchor(page, section: str):
  for term in _section_search_terms(section):
    rects = page.search_for(term)
    if rects:
      return min(rects, key=lambda rect: rect.y0)

  tokens = [token for token in re.findall(r"[a-z0-9]+", str(section or "").lower()) if len(token) > 2]
  if not tokens:
    return None

  best_rect = None
  best_score = 0
  for block in page.get_text("blocks"):
    x0, y0, x1, y1, text, *_ = block
    normalized = " ".join(str(text or "").lower().split())
    score = sum(1 for token in tokens if token in normalized)
    if score > best_score:
      best_score = score
      best_rect = fitz.Rect(x0, y0, x1, y1)

  return best_rect if best_score >= min(2, len(tokens)) else None


def _section_tokens(section: str):
  tokens = [token for token in re.findall(r"[a-z0-9]+", str(section or "").lower()) if len(token) > 2]
  stop_words = {
    "last",
    "days",
    "page",
    "figure",
    "card",
    "section",
    "clicking",
    "shown",
    "display",
  }
  return [token for token in tokens if token not in stop_words]


def _image_context_score(page, rect, section: str):
  tokens = _section_tokens(section)
  if not tokens:
    return 0

  expanded = fitz.Rect(
    rect.x0 - 24,
    rect.y0 - 120,
    rect.x1 + 24,
    rect.y1 + 120,
  ) & page.rect

  nearby_text = " ".join(
    str(block[4] or "")
    for block in page.get_text("blocks", clip=expanded)
  ).lower()
  if not nearby_text:
    return 0

  score = 0
  for token in tokens:
    if token in nearby_text:
      score += 1

  return score


def _find_best_figure_region(document, page: int, section: str):
  candidate_pages = []
  for candidate in (page, page + 1, page - 1):
    if 1 <= candidate <= len(document) and candidate not in candidate_pages:
      candidate_pages.append(candidate)

  best_match = None
  best_score = float("-inf")
  for candidate in candidate_pages:
    pdf_page = document.load_page(candidate - 1)
    anchor = _find_section_anchor(pdf_page, section)
    image_rects = []
    for image in pdf_page.get_images(full=True):
      xref = image[0]
      image_rects.extend(pdf_page.get_image_rects(xref))

    image_rects = [rect for rect in image_rects if rect.width >= 120 and rect.height >= 90]
    if not image_rects:
      continue

    for rect in image_rects:
      context_score = _image_context_score(pdf_page, rect, section)
      area_score = (rect.width * rect.height) / 10000.0

      if anchor is not None:
        vertical_distance = abs(rect.y0 - anchor.y1)
        if rect.y0 >= anchor.y1 - 16:
          proximity = 2.5
        else:
          proximity = 0.0
        score = (context_score * 20.0) + proximity - (vertical_distance / 1200.0) + area_score
      else:
        score = (context_score * 20.0) + area_score

      if score > best_score:
        best_score = score
        best_match = (candidate, rect + (-10, -10, 10, 10))

  return best_match


@app.post("/chat")
def chat(request: ChatRequest):
    try:
        result = rag.run(
            request.question,
            history=[turn.model_dump() for turn in request.history],
            where=request.to_where(),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return result


@app.post("/chat/stream")
def chat_stream(request: ChatRequest):
    history = [turn.model_dump() for turn in request.history]
    where = request.to_where()

    def event_stream():
        try:
            for item in rag.stream(request.question, history=history, where=where):
                yield json.dumps(item, ensure_ascii=False) + "\n"
        except RuntimeError as exc:
            yield json.dumps({"type": "error", "detail": str(exc)}, ensure_ascii=False) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


@app.post("/feedback/like")
def save_like(request: FeedbackRequest):
    feedback_store.save_like(
        message_id=request.message_id,
        question=request.question,
        answer=request.answer,
        created_at=request.created_at,
    )
    return {"status": "saved", "feedback": "like"}


@app.post("/feedback/dislike")
def save_dislike(request: FeedbackRequest):
    feedback_store.save_dislike(
        message_id=request.message_id,
        question=request.question,
        answer=request.answer,
        created_at=request.created_at,
    )
    return {"status": "saved", "feedback": "dislike"}


@app.get("/kb-pages/{collection}/{page}")
def kb_page_snapshot(collection: str, page: int, zoom: float = 1.7):
    if page < 1:
      raise HTTPException(status_code=400, detail="Page must be >= 1.")
    if zoom <= 0 or zoom > 3:
      raise HTTPException(status_code=400, detail="Zoom must be > 0 and <= 3.")

    pdf_path = _resolve_pdf_for_collection(collection)
    if not pdf_path:
      raise HTTPException(
        status_code=404,
        detail=f"No source PDF found for collection '{collection}'.",
      )

    try:
      with fitz.open(pdf_path) as document:
        if page > len(document):
          raise HTTPException(
            status_code=404,
            detail=f"Page {page} is out of bounds for '{pdf_path.name}'.",
          )

        pdf_page = document.load_page(page - 1)
        pixmap = pdf_page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        return Response(content=pixmap.tobytes("png"), media_type="image/png")
    except HTTPException:
      raise
    except Exception as exc:
      raise HTTPException(status_code=500, detail="Failed to render PDF page image.") from exc


@app.get("/kb-figures/{collection}/{page}")
def kb_figure_snapshot(collection: str, page: int, section: str = "", context: str = "", zoom: float = 2.2):
    if page < 1:
      raise HTTPException(status_code=400, detail="Page must be >= 1.")
    if zoom <= 0 or zoom > 4:
      raise HTTPException(status_code=400, detail="Zoom must be > 0 and <= 4.")

    pdf_path = _resolve_pdf_for_collection(collection)
    if not pdf_path:
      raise HTTPException(
        status_code=404,
        detail=f"No source PDF found for collection '{collection}'.",
      )

    try:
      with fitz.open(pdf_path) as document:
        selected_figure = image_selector.select_figure(
          collection=collection,
          pdf_path=pdf_path,
          page=page,
          section=section,
          context=context,
          use_model=False,
        )
        if selected_figure:
          target_page = int(selected_figure["page"])
          clip_rect = fitz.Rect(selected_figure["clip_rect"])
          pdf_page = document.load_page(target_page - 1)
          clip_rect = clip_rect & pdf_page.rect
          pixmap = pdf_page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip_rect, alpha=False)
          return Response(content=pixmap.tobytes("png"), media_type="image/png")

        selected_image = image_selector.select_image(
          collection=collection,
          page=page,
          section=section,
          use_model=False,
        )
        if selected_image:
          image_path = Path(selected_image["image_path"])
          return Response(
            content=image_path.read_bytes(),
            media_type=selected_image["media_type"],
          )

        match = _find_best_figure_region(document, page=page, section=section or context)
        if match:
          target_page, clip_rect = match
          pdf_page = document.load_page(target_page - 1)
          clip_rect = clip_rect & pdf_page.rect
          pixmap = pdf_page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip_rect, alpha=False)
          return Response(content=pixmap.tobytes("png"), media_type="image/png")

        if page > len(document):
          raise HTTPException(
            status_code=404,
            detail=f"Page {page} is out of bounds for '{pdf_path.name}'.",
          )

        pdf_page = document.load_page(page - 1)
        pixmap = pdf_page.get_pixmap(matrix=fitz.Matrix(1.8, 1.8), alpha=False)
        return Response(content=pixmap.tobytes("png"), media_type="image/png")
    except HTTPException:
      raise
    except Exception as exc:
      raise HTTPException(status_code=500, detail="Failed to render figure image.") from exc


@app.get("/chroma/collections")
def chroma_collections():
    try:
        return {"collections": list_collections()}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail="Failed to load Chroma collections."
        ) from exc


@app.get("/chroma/collections/{name}")
def chroma_collection_preview(name: str, limit: int = 5):
    try:
        return get_collection_preview(name, limit=limit)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to load Chroma collection '{name}'."
        ) from exc


@app.get("/chroma/collections/{name}/overview")
def chroma_collection_overview(name: str, sample_size: int = 25):
    try:
        return get_collection_overview(name, sample_size=sample_size)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to load overview for '{name}'."
        ) from exc


@app.get("/chroma/collections/{name}/records")
def chroma_collection_records(name: str, offset: int = 0, limit: int = 25):
    try:
        return get_collection_records(name, offset=offset, limit=limit)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to load records for '{name}'."
        ) from exc


@app.get("/chroma-admin", response_class=HTMLResponse)
def chroma_admin():
    return """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Chroma Admin</title>
    <style>
      :root {
        color-scheme: light;
        --bg: #eef3ef;
        --panel: rgba(255, 255, 255, 0.94);
        --panel-strong: #ffffff;
        --text: #18271f;
        --muted: #617267;
        --line: #d5ddd7;
        --accent: #116149;
        --accent-strong: #0b4c39;
        --accent-soft: #e0f1ea;
        --sun: #f7f0d2;
        --shadow: 0 20px 50px rgba(22, 39, 31, 0.09);
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: "Segoe UI", system-ui, sans-serif;
        background:
          radial-gradient(circle at top left, rgba(247, 240, 210, 0.85), transparent 30%),
          radial-gradient(circle at top right, rgba(17, 97, 73, 0.14), transparent 28%),
          linear-gradient(180deg, #f8fbf8, var(--bg));
        color: var(--text);
      }
      .shell {
        max-width: 1380px;
        margin: 0 auto;
        padding: 28px 20px 42px;
      }
      .header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 18px;
        margin-bottom: 20px;
      }
      h1 {
        margin: 0;
        font-size: 38px;
        letter-spacing: -0.03em;
      }
      .subtitle {
        margin-top: 8px;
        color: var(--muted);
        max-width: 700px;
      }
      .panel {
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 24px;
        padding: 20px;
        box-shadow: var(--shadow);
        backdrop-filter: blur(8px);
      }
      .grid {
        display: grid;
        grid-template-columns: 320px minmax(0, 1fr);
        gap: 20px;
      }
      .right-column {
        display: grid;
        gap: 20px;
      }
      .button {
        border: 0;
        border-radius: 12px;
        background: var(--accent);
        color: white;
        padding: 10px 14px;
        font-weight: 600;
        cursor: pointer;
        transition: transform 0.18s ease, background 0.18s ease;
      }
      .button:hover {
        background: var(--accent-strong);
        transform: translateY(-1px);
      }
      .button.secondary {
        background: var(--sun);
        color: var(--text);
      }
      .button.secondary:hover {
        background: #efe5b8;
      }
      .collections {
        display: grid;
        gap: 12px;
      }
      .collection-card {
        border: 1px solid var(--line);
        border-radius: 18px;
        padding: 14px;
        background: #fbfdfa;
        cursor: pointer;
        text-align: left;
        transition: transform 0.18s ease, border-color 0.18s ease, background 0.18s ease;
      }
      .collection-card:hover {
        transform: translateY(-1px);
        border-color: #b8c8bd;
      }
      .collection-card.active {
        border-color: var(--accent);
        background: var(--accent-soft);
      }
      .collection-name {
        font-weight: 700;
      }
      .meta {
        margin-top: 8px;
        color: var(--muted);
        font-size: 14px;
      }
      .toolbar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 12px;
        margin-bottom: 18px;
      }
      .toolbar-group {
        display: flex;
        gap: 10px;
        align-items: center;
        flex-wrap: wrap;
      }
      .pill {
        display: inline-flex;
        align-items: center;
        padding: 6px 10px;
        border-radius: 999px;
        background: #f2f6f3;
        color: var(--muted);
        border: 1px solid var(--line);
        font-size: 13px;
        font-weight: 600;
      }
      .hero {
        background:
          linear-gradient(135deg, rgba(17, 97, 73, 0.08), rgba(247, 240, 210, 0.55)),
          var(--panel-strong);
      }
      .stats {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 12px;
        margin-top: 18px;
      }
      .stat-card {
        border: 1px solid var(--line);
        border-radius: 18px;
        background: #fcfdfb;
        padding: 14px;
      }
      .stat-card.interactive {
        cursor: pointer;
        transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
      }
      .stat-card.interactive:hover {
        transform: translateY(-1px);
        border-color: #b8c8bd;
        box-shadow: 0 12px 24px rgba(22, 39, 31, 0.08);
      }
      .stat-label {
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--muted);
      }
      .stat-value {
        margin-top: 8px;
        font-size: 24px;
        font-weight: 700;
      }
      .metadata-box {
        margin-top: 16px;
        padding: 14px;
        border-radius: 18px;
        border: 1px solid var(--line);
        background: #fbfdfa;
      }
      .muted {
        color: var(--muted);
      }
      .search {
        width: 100%;
        border: 1px solid var(--line);
        border-radius: 14px;
        padding: 11px 14px;
        font: inherit;
        background: #fff;
      }
      .records {
        display: grid;
        gap: 14px;
      }
      .record-card {
        border: 1px solid var(--line);
        border-radius: 18px;
        background: #fff;
        padding: 16px;
      }
      .record-top {
        display: flex;
        justify-content: space-between;
        gap: 16px;
        align-items: flex-start;
      }
      .record-id {
        font-weight: 700;
        word-break: break-word;
      }
      .record-document {
        margin-top: 12px;
        line-height: 1.55;
        white-space: pre-wrap;
        word-break: break-word;
      }
      .record-meta-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 10px;
        margin-top: 14px;
      }
      .mini-card {
        border-radius: 14px;
        background: #f6faf7;
        border: 1px solid var(--line);
        padding: 12px;
      }
      .mini-label {
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--muted);
        margin-bottom: 6px;
      }
      .chip-list {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
      }
      .chip {
        display: inline-flex;
        padding: 6px 10px;
        border-radius: 999px;
        background: var(--accent-soft);
        color: var(--accent-strong);
        font-size: 12px;
        font-weight: 700;
      }
      .json {
        margin: 0;
        white-space: pre-wrap;
        word-break: break-word;
        background: #f7f9fc;
        border: 1px solid var(--line);
        border-radius: 14px;
        padding: 14px;
        max-height: 300px;
        overflow: auto;
        font-size: 13px;
      }
      .empty {
        color: var(--muted);
        padding: 14px 0;
      }
      .footer-bar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 14px;
        margin-top: 18px;
        flex-wrap: wrap;
      }
      .page-controls {
        display: flex;
        gap: 10px;
        align-items: center;
      }
      .page-label {
        color: var(--muted);
        font-weight: 600;
      }
      .records-toolbar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 12px;
        margin-bottom: 14px;
        flex-wrap: wrap;
      }
      .segmented {
        display: inline-flex;
        gap: 8px;
        align-items: center;
        flex-wrap: wrap;
      }
      .button.active {
        background: var(--accent-strong);
      }
      .raw-panel {
        max-height: 420px;
      }
      h2, h3 {
        margin: 0;
      }
      h3 {
        font-size: 18px;
      }
      code {
        font-family: Consolas, monospace;
      }
      .empty {
        color: var(--muted);
      }
      @media (max-width: 900px) {
        .grid { grid-template-columns: 1fr; }
        .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      }
      @media (max-width: 640px) {
        .stats { grid-template-columns: 1fr; }
        .header, .toolbar, .record-top, .footer-bar {
          flex-direction: column;
          align-items: stretch;
        }
      }
    </style>
  </head>
  <body>
    <div class="shell">
      <section class="panel hero">
        <div class="header">
          <div>
            <h1>Chroma Admin</h1>
            <div class="subtitle">
              Inspect collections as readable records. This view highlights counts, metadata keys,
              document content, and embedding shape so you can understand what the RAG pipeline is using.
            </div>
          </div>
          <div class="toolbar-group">
            <span class="pill">Backend UI</span>
            <button class="button" onclick="loadCollections()">Refresh</button>
          </div>
        </div>
      </section>
      <div style="height: 20px"></div>
      <div class="grid">
        <section class="panel">
          <div class="toolbar">
            <div>
              <h2>Collections</h2>
              <div class="muted">Choose a collection to inspect its data shape.</div>
            </div>
            <span id="collection-count-pill" class="pill">0 collections</span>
          </div>
          <div id="collections" class="collections">
            <div class="empty">Loading collections...</div>
          </div>
        </section>
        <div class="right-column">
          <section class="panel">
            <div class="toolbar">
              <div>
                <h2 id="overview-title">Collection overview</h2>
                <div id="overview-subtitle" class="muted">Select a collection to inspect it.</div>
              </div>
              <div class="toolbar-group">
                <button class="button secondary" onclick="loadSelectedCollection()">Reload selection</button>
              </div>
            </div>
            <div id="overview-content" class="empty">Collection summary will appear here.</div>
          </section>
          <section class="panel" id="records-panel">
            <div class="toolbar">
              <div>
                <h2>Records</h2>
                <div class="muted">Browse stored chunks with metadata and embedding details, or inspect them one by one.</div>
              </div>
              <div class="toolbar-group">
                <input id="record-search" class="search" type="search" placeholder="Filter loaded records by text, id, or metadata..." oninput="renderRecords()" />
              </div>
            </div>
            <div class="records-toolbar">
              <div id="record-mode-label" class="page-label">Loaded documents</div>
              <div class="segmented">
                <button id="single-view-button" class="button secondary" type="button" onclick="setRecordViewMode('single')">One by one</button>
                <button id="list-view-button" class="button secondary" type="button" onclick="setRecordViewMode('list')">Loaded page</button>
                <button id="prev-record-button" class="button secondary" type="button" onclick="changeRecord(-1)">Previous document</button>
                <button id="next-record-button" class="button" type="button" onclick="changeRecord(1)">Next document</button>
              </div>
            </div>
            <div id="records" class="records">
              <div class="empty">No records loaded yet.</div>
            </div>
            <div class="footer-bar">
              <div id="page-label" class="page-label">Page 1</div>
              <div class="page-controls">
                <button id="prev-button" class="button secondary" onclick="changePage(-1)">Previous</button>
                <button id="next-button" class="button" onclick="changePage(1)">Next</button>
              </div>
            </div>
          </section>
          <section class="panel">
            <div class="toolbar">
              <div>
                <h2>Raw Preview</h2>
                <div class="muted">Useful when you want the exact JSON coming back from Chroma.</div>
              </div>
            </div>
            <pre id="raw-output" class="json raw-panel">Select a collection to inspect raw JSON.</pre>
          </section>
        </div>
      </div>
    </div>
    <script>
      let selectedCollection = null;
      let cachedCollections = [];
      let currentOverview = null;
      let currentRecords = [];
      let currentOffset = 0;
      let recordViewMode = "single";
      let currentRecordIndex = 0;
      const pageSize = 12;

      function renderCollections(collections) {
        const root = document.getElementById("collections");
        document.getElementById("collection-count-pill").textContent = `${collections.length} collection${collections.length === 1 ? "" : "s"}`;

        if (!collections.length) {
          root.innerHTML = '<div class="empty">No collections found.</div>';
          return;
        }

        root.innerHTML = "";
        collections.forEach((collection) => {
          const card = document.createElement("button");
          card.className = "collection-card";
          card.type = "button";
          if (collection.name === selectedCollection) {
            card.classList.add("active");
          }
          card.innerHTML = `
            <div class="collection-name">${collection.name}</div>
            <div class="meta">Documents: ${collection.count ?? "unknown"}</div>
            <div class="meta">Metadata keys: ${Object.keys(collection.metadata || {}).length}</div>
          `;
          card.onclick = () => selectCollection(collection.name);
          root.appendChild(card);
        });
      }

      function escapeHtml(value) {
        return String(value ?? "")
          .replaceAll("&", "&amp;")
          .replaceAll("<", "&lt;")
          .replaceAll(">", "&gt;")
          .replaceAll('"', "&quot;")
          .replaceAll("'", "&#39;");
      }

      function formatValue(value) {
        if (value === null || value === undefined || value === "") {
          return '<span class="muted">None</span>';
        }

        if (typeof value === "object") {
          return `<pre class="json">${escapeHtml(JSON.stringify(value, null, 2))}</pre>`;
        }

        return escapeHtml(value);
      }

      function renderOverview() {
        const root = document.getElementById("overview-content");

        if (!currentOverview) {
          root.innerHTML = '<div class="empty">Collection summary will appear here.</div>';
          return;
        }

        const collection = currentOverview.collection || {};
        const summary = currentOverview.summary || {};
        const metadataKeys = summary.metadata_keys || [];
        const sampleRecords = currentOverview.sample_records || [];

        root.innerHTML = `
          <div class="stats">
            <button class="stat-card interactive" type="button" onclick="openDocumentsView()">
              <div class="stat-label">Documents</div>
              <div class="stat-value">${collection.count ?? "?"}</div>
            </button>
            <div class="stat-card">
              <div class="stat-label">Metadata Keys</div>
              <div class="stat-value">${metadataKeys.length}</div>
            </div>
            <div class="stat-card">
              <div class="stat-label">Avg Doc Length</div>
              <div class="stat-value">${summary.average_document_length ?? 0}</div>
            </div>
            <div class="stat-card">
              <div class="stat-label">Embedding Size</div>
              <div class="stat-value">${summary.embedding_size ?? "?"}</div>
            </div>
          </div>
          <div class="metadata-box">
            <h3>Collection metadata</h3>
            <div style="margin-top: 10px;">${formatValue(collection.metadata || {})}</div>
          </div>
          <div class="metadata-box">
            <h3>Detected metadata keys</h3>
            <div class="chip-list" style="margin-top: 12px;">
              ${metadataKeys.length ? metadataKeys.map((key) => `<span class="chip">${escapeHtml(key)}</span>`).join("") : '<span class="muted">No metadata keys found in sampled records.</span>'}
            </div>
          </div>
          <div class="metadata-box">
            <h3>Sample records</h3>
            <div class="muted" style="margin-top: 8px;">Quick snapshot of the first few rows in this collection.</div>
            <pre class="json" style="margin-top: 12px;">${escapeHtml(JSON.stringify(sampleRecords, null, 2))}</pre>
          </div>
        `;
      }

      function recordMatchesFilter(record, query) {
        if (!query) {
          return true;
        }

        const haystack = [
          record.id,
          record.document,
          JSON.stringify(record.metadata || {}),
          JSON.stringify(record.metadata_keys || []),
        ].join(" ").toLowerCase();

        return haystack.includes(query);
      }

      function getFilteredRecords() {
        const query = document.getElementById("record-search").value.trim().toLowerCase();
        return currentRecords.filter((record) => recordMatchesFilter(record, query));
      }

      function clampRecordIndex(records) {
        if (!records.length) {
          currentRecordIndex = 0;
          return;
        }

        if (currentRecordIndex < 0) {
          currentRecordIndex = 0;
        }

        if (currentRecordIndex >= records.length) {
          currentRecordIndex = records.length - 1;
        }
      }

      function renderRecordCard(record) {
        return `
          <article class="record-card">
            <div class="record-top">
              <div>
                <div class="record-id">${escapeHtml(record.id)}</div>
                <div class="meta">Length: ${record.document_length} characters</div>
              </div>
              <div class="chip-list">
                <span class="chip">${(record.metadata_keys || []).length} metadata keys</span>
                <span class="chip">Embedding: ${record.embedding_size ?? "?"}</span>
              </div>
            </div>
            <div class="record-document">${escapeHtml(record.document || "") || '<span class="muted">No document text</span>'}</div>
            <div class="record-meta-grid">
              <div class="mini-card">
                <div class="mini-label">Metadata keys</div>
                <div class="chip-list">
                  ${(record.metadata_keys || []).length ? record.metadata_keys.map((key) => `<span class="chip">${escapeHtml(key)}</span>`).join("") : '<span class="muted">No metadata</span>'}
                </div>
              </div>
              <div class="mini-card">
                <div class="mini-label">Metadata</div>
                ${formatValue(record.metadata || {})}
              </div>
              <div class="mini-card">
                <div class="mini-label">Embedding preview</div>
                ${formatValue(record.embedding_preview || null)}
              </div>
            </div>
          </article>
        `;
      }

      function renderRecords() {
        const root = document.getElementById("records");
        const records = getFilteredRecords();

        if (!currentRecords.length) {
          root.innerHTML = '<div class="empty">No records loaded yet.</div>';
          updateRecordViewer([]);
          return;
        }

        if (!records.length) {
          root.innerHTML = '<div class="empty">No loaded records match your filter.</div>';
          updateRecordViewer([]);
          return;
        }

        clampRecordIndex(records);

        if (recordViewMode === "single") {
          root.innerHTML = renderRecordCard(records[currentRecordIndex]);
        } else {
          root.innerHTML = records.map((record) => renderRecordCard(record)).join("");
        }

        updateRecordViewer(records);
      }

      function updateRecordViewer(records) {
        const singleButton = document.getElementById("single-view-button");
        const listButton = document.getElementById("list-view-button");
        const prevRecordButton = document.getElementById("prev-record-button");
        const nextRecordButton = document.getElementById("next-record-button");
        const label = document.getElementById("record-mode-label");

        singleButton.classList.toggle("active", recordViewMode === "single");
        singleButton.classList.toggle("secondary", recordViewMode !== "single");
        listButton.classList.toggle("active", recordViewMode === "list");
        listButton.classList.toggle("secondary", recordViewMode !== "list");

        if (!records.length) {
          label.textContent = "No matching documents";
          prevRecordButton.disabled = true;
          nextRecordButton.disabled = true;
          return;
        }

        if (recordViewMode === "single") {
          label.textContent = `Document ${currentRecordIndex + 1} of ${records.length} on this loaded page`;
          prevRecordButton.disabled = currentRecordIndex <= 0;
          nextRecordButton.disabled = currentRecordIndex >= records.length - 1;
          return;
        }

        label.textContent = `Showing ${records.length} loaded documents on this page`;
        prevRecordButton.disabled = true;
        nextRecordButton.disabled = true;
      }

      function setRecordViewMode(mode) {
        recordViewMode = mode;
        renderRecords();
      }

      function changeRecord(direction) {
        const records = getFilteredRecords();
        if (!records.length || recordViewMode !== "single") {
          return;
        }

        const nextIndex = currentRecordIndex + direction;
        if (nextIndex < 0 || nextIndex >= records.length) {
          return;
        }

        currentRecordIndex = nextIndex;
        renderRecords();
      }

      function openDocumentsView() {
        recordViewMode = "single";
        currentRecordIndex = 0;
        renderRecords();
        document.getElementById("records-panel").scrollIntoView({ behavior: "smooth", block: "start" });
      }

      function updatePageControls(response) {
        const page = Math.floor((response.offset || 0) / (response.limit || pageSize)) + 1;
        const total = response.count ?? 0;
        const start = total ? response.offset + 1 : 0;
        const end = response.offset + response.returned;

        document.getElementById("page-label").textContent = `Page ${page} • Showing ${start}-${end} of ${total}`;
        document.getElementById("prev-button").disabled = response.offset <= 0;
        document.getElementById("next-button").disabled = !response.has_next_page;
      }

      async function selectCollection(name) {
        selectedCollection = name;
        currentOffset = 0;
        currentRecordIndex = 0;
        renderCollections(cachedCollections);
        await loadSelectedCollection();
      }

      async function loadCollections() {
        const root = document.getElementById("collections");
        root.innerHTML = '<div class="empty">Loading collections...</div>';

        try {
          const response = await fetch("/chroma/collections");
          const data = await response.json();

          if (!response.ok) {
            throw new Error(data.detail || "Failed to load collections");
          }

          cachedCollections = data.collections || [];
          if (!cachedCollections.length) {
            renderCollections(cachedCollections);
            document.getElementById("overview-content").innerHTML = '<div class="empty">No collections available yet. Run <code>python backend\\scripts\\run_chunking.py --ingest-chroma</code> if needed.</div>';
            document.getElementById("records").innerHTML = '<div class="empty">No records to show.</div>';
            document.getElementById("raw-output").textContent = "No collections available.";
            return;
          }

          if (!selectedCollection || !cachedCollections.some((collection) => collection.name === selectedCollection)) {
            selectedCollection = cachedCollections[0].name;
          }

          renderCollections(cachedCollections);
          await loadSelectedCollection();
        } catch (error) {
          root.innerHTML = `<div class="empty">${error.message}</div>`;
          document.getElementById("overview-content").innerHTML = `<div class="empty">${error.message}</div>`;
          document.getElementById("records").innerHTML = `<div class="empty">${error.message}</div>`;
          document.getElementById("raw-output").textContent = error.message;
        }
      }

      async function loadSelectedCollection() {
        if (!selectedCollection) {
          return;
        }

        document.getElementById("overview-title").textContent = `Collection overview: ${selectedCollection}`;
        document.getElementById("overview-subtitle").textContent = "Loading collection details...";
        document.getElementById("overview-content").innerHTML = '<div class="empty">Loading overview...</div>';
        document.getElementById("records").innerHTML = '<div class="empty">Loading records...</div>';
        document.getElementById("raw-output").textContent = "Loading raw preview...";
        renderCollections(cachedCollections);

        try {
          const [overviewResponse, recordsResponse, previewResponse] = await Promise.all([
            fetch(`/chroma/collections/${encodeURIComponent(selectedCollection)}/overview?sample_size=25`),
            fetch(`/chroma/collections/${encodeURIComponent(selectedCollection)}/records?offset=${currentOffset}&limit=${pageSize}`),
            fetch(`/chroma/collections/${encodeURIComponent(selectedCollection)}?limit=5`),
          ]);

          const overviewData = await overviewResponse.json();
          const recordsData = await recordsResponse.json();
          const previewData = await previewResponse.json();

          if (!overviewResponse.ok) {
            throw new Error(overviewData.detail || "Failed to load collection overview");
          }
          if (!recordsResponse.ok) {
            throw new Error(recordsData.detail || "Failed to load collection records");
          }
          if (!previewResponse.ok) {
            throw new Error(previewData.detail || "Failed to load collection preview");
          }

          currentOverview = overviewData;
          currentRecords = recordsData.records || [];
          currentRecordIndex = 0;
          document.getElementById("overview-subtitle").textContent = `Browsing ${recordsData.count ?? 0} stored records`;
          renderOverview();
          renderRecords();
          updatePageControls(recordsData);
          document.getElementById("raw-output").textContent = JSON.stringify(previewData, null, 2);
        } catch (error) {
          currentOverview = null;
          currentRecords = [];
          currentRecordIndex = 0;
          document.getElementById("overview-subtitle").textContent = error.message;
          document.getElementById("overview-content").innerHTML = `<div class="empty">${error.message}</div>`;
          document.getElementById("records").innerHTML = `<div class="empty">${error.message}</div>`;
          document.getElementById("raw-output").textContent = error.message;
          updatePageControls({ offset: 0, limit: pageSize, returned: 0, count: 0, has_next_page: false });
        }
      }

      function changePage(direction) {
        const nextOffset = currentOffset + (direction * pageSize);
        if (nextOffset < 0) {
          return;
        }

        currentOffset = nextOffset;
        loadSelectedCollection();
      }

      loadCollections();
    </script>
  </body>
</html>
"""
