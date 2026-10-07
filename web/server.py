"""FastAPI web server to serve the BestBuyTool Web UI."""

import os
import sys
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, Query, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Add parent directory to path to import other modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers.registry import get_scrapers, list_suppliers
from engine.search import SearchEngine
from engine.comparator import sort_by_price

logger = logging.getLogger("BestBuyTool.Web")

app = FastAPI(
    title="BestBuyTool API",
    description="Web scraping comparison search engine backend API",
    version="1.0.0",
)

# Thread pool for CPU/IO-bound scraping jobs
executor = ThreadPoolExecutor(max_workers=10)

# Setup paths
WEB_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(WEB_DIR, "static")

# Ensure static dir exists
os.makedirs(STATIC_DIR, exist_ok=True)


@app.get("/api/suppliers")
def get_suppliers():
    """Retrieve list of configured suppliers."""
    try:
        return list_suppliers()
    except Exception as e:
        logger.error("Failed to list suppliers: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/search")
async def run_search(
    q: str = Query(..., min_length=1, description="Cuvantul cheie cautat"),
    suppliers: str = Query(None, description="Comma-separated IDs of suppliers to use"),
    country: str = Query(None, description="Filter suppliers by country code (RO, PL, etc.)"),
    force_scrape: bool = Query(False, description="Force scraping bypassing link_only constraints"),
    ai_optimize: bool = Query(False, description="Whether to optimize the search query using Gemini AI"),
    v: int = Query(1, description="Response format: 1 = plain list of products (old UI), 2 = full outcome"),
):
    """Run search query across suppliers concurrently."""
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Search query cannot be empty.")

    # Parse supplier list
    supplier_ids = [s.strip() for s in suppliers.split(",") if s.strip()] if suppliers else None
    country_code = country.strip().upper() if country else None

    # Load scrapers
    scrapers = get_scrapers(
        supplier_ids=supplier_ids,
        country=country_code,
        force_scrape=force_scrape,
    )
    if not scrapers:
        raise HTTPException(
            status_code=400,
            detail="Niciun furnizor selectat sau disponibil cu filtrele selectate.",
        )

    # Execute search in thread pool to avoid blocking the event loop
    loop = asyncio.get_running_loop()
    try:
        engine = SearchEngine(scrapers)
        # SearchEngine.search runs scrapers in a ThreadPoolExecutor internally
        outcome = await loop.run_in_executor(executor, engine.search, query, ai_optimize)
        outcome.products = sort_by_price(outcome.products)
        if v < 2:
            # A browser still running a cached old app.js expects a bare list.
            return [p.to_dict() for p in outcome.products]
        return outcome.to_dict()
    except Exception as e:
        logger.exception("Search failed")
        raise HTTPException(status_code=500, detail=f"Search failed: {type(e).__name__}")


@app.middleware("http")
async def no_cache_ui(request, call_next):
    """Make the browser revalidate the UI files, so a code update is never mixed with a stale app.js."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


# Serve Web UI files
@app.get("/")
def serve_index():
    """Serve the main index.html file."""
    index_file = os.path.join(STATIC_DIR, "index.html")
    if not os.path.exists(index_file):
        raise HTTPException(status_code=404, detail="Frontend index.html is missing.")
    return FileResponse(index_file)


# Mount remaining static files (CSS, JS, etc.) if folder is not empty
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
