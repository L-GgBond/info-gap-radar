import httpx
from bs4 import BeautifulSoup

USER_AGENT = "InfoGapRadar/0.2"
MAX_TEXT = 12000


async def fetch_article(url: str):
    """抓取文章正文，去掉导航/脚本等噪音，返回 {title, text}。"""
    async with httpx.AsyncClient(
        timeout=18, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form", "iframe", "noscript"]):
        tag.decompose()
    root = soup.find("article") or soup.find("main") or soup.body or soup
    blocks = []
    for element in root.find_all(["p", "h1", "h2", "h3", "h4", "li", "blockquote"]):
        text = element.get_text(" ", strip=True)
        if len(text) >= 2:
            blocks.append(text)
    text = "\n\n".join(blocks)
    if not text:
        text = root.get_text("\n", strip=True)
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    return {"title": title, "text": text[:MAX_TEXT]}


def detect_language(text: str) -> str:
    """简单启发式语言检测：中/日/韩字符占比高判定为中文，否则按英文处理。"""
    sample = (text or "")[:2000]
    cjk = sum(
        1
        for ch in sample
        if "\u4e00" <= ch <= "\u9fff" or "\u3040" <= ch <= "\u30ff" or "\uac00" <= ch <= "\ud7af"
    )
    letters = sum(1 for ch in sample if ch.isalpha())
    if letters == 0:
        return "zh"
    return "zh" if cjk / letters > 0.3 else "en"
