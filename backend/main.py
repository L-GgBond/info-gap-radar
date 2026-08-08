import argparse
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
import uvicorn

from services.collectors import collect_items, collect_custom_site
from services.insights import build_report
from services.storage import init_db, list_items, save_items, get_item, save_report


app = FastAPI(title="信息差雷达 API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CrawlRequest(BaseModel):
    source: str = "all"


class CustomSiteRequest(BaseModel):
    url: HttpUrl


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/items")
def items(category: str | None = None):
    return {"items": list_items(category)}


@app.post("/crawl")
async def crawl(payload: CrawlRequest):
    fresh_items = await collect_items(payload.source)
    save_items(fresh_items)
    return {"saved": len(fresh_items), "items": fresh_items}


@app.post("/crawl/custom")
async def crawl_custom(payload: CustomSiteRequest):
    fresh_items = await collect_custom_site(str(payload.url))
    save_items(fresh_items)
    return {"saved": len(fresh_items), "items": fresh_items}


@app.post("/items/{item_id}/report")
async def report(item_id: int):
    item = get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    markdown = build_report(item)
    save_report(item_id, markdown)
    return {"report": markdown}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    uvicorn.run("main:app", host="127.0.0.1", port=args.port, reload=False)
