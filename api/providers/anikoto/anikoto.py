"""
Anikoto provider - fetches episodes and video links from anikotoapi.site
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
import aiohttp
from ..video_utils import encode_payload

logger = logging.getLogger(__name__)

BASE_URL = "https://anikotoapi.site"

UPSTREAM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

class AnikotoScraper:
    def __init__(self, timeout: int = 20):
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._semaphore = asyncio.Semaphore(3)

    async def _get_json(self, session: aiohttp.ClientSession, url: str) -> Optional[Any]:
        try:
            async with self._semaphore:
                async with session.get(url, headers=UPSTREAM_HEADERS) as r:
                    if r.status != 200:
                        logger.warning(f"[Anikoto] GET {url} -> {r.status}")
                        return None
                    return await r.json(content_type=None)
        except Exception as e:
            logger.warning(f"[Anikoto] GET {url} failed: {e}")
            return None

    async def build_provider_blocks(self, anilist_id: int, anime_title: str = "") -> Dict[str, Dict[str, Any]]:
        """
        Maps the requested anime via its ID and formats the structural 
        episode block for sub/dub selection required by your layout.
        """
        url = f"{BASE_URL}/series/{anilist_id}"
        async with aiohttp.ClientSession(timeout=self._timeout) as session:
            data = await self._get_json(session, url)

        if not data or not isinstance(data, dict) or "episodes" not in data:
            return {}

        sub_eps: List[Dict[str, Any]] = []
        dub_eps: List[Dict[str, Any]] = []

        for ep in data.get("episodes", []):
            ep_num = ep.get("number")
            ep_title = ep.get("title") or f"Episode {ep_num}"
            
            # Use distinct parsing structures matching your custom dynamic watch paths
            if ep.get("embed_url", {}).get("sub"):
                sub_eps.append({
                    "id": f"watch/anikoto/{anilist_id}/sub/{ep_num}",
                    "number": ep_num,
                    "title": ep_title,
                    "filler": False,
                })
            if ep.get("embed_url", {}).get("dub"):
                dub_eps.append({
                    "id": f"watch/anikoto/{anilist_id}/dub/{ep_num}",
                    "number": ep_num,
                    "title": ep_title,
                    "filler": False,
                })

        if not sub_eps and not dub_eps:
            return {}

        return {
            "anikoto-main": {
                "meta": {"title": anime_title or data.get("title", "Anikoto")},
                "episodes": {"sub": sub_eps, "dub": dub_eps},
                "_anikoto": True
            }
        }

    async def get_sources(self, anilist_id: int, ep_num: Any, category: str = "sub") -> Dict[str, Any]:
        """Fetches embed stream targets and encodes payloads safely."""
        url = f"{BASE_URL}/series/{anilist_id}"
        async with aiohttp.ClientSession(timeout=self._timeout) as session:
            data = await self._get_json(session, url)

        if not data or "episodes" not in data:
            return {"error": "no_sources", "message": "No response from Anikoto."}

        target_ep = None
        for ep in data.get("episodes", []):
            if str(ep.get("number")) == str(ep_num):
                target_ep = ep
                break

        if not target_ep:
            return {"error": "no_sources", "message": f"Episode {ep_num} not found."}

        embeds = target_ep.get("embed_url", {})
        stream_url = embeds.get("sub") if category == "sub" else embeds.get("dub")

        if not stream_url:
            return {"error": "no_sources", "message": f"No streaming link available for language selection."}

        # Securely pass the stream source down to your running Go proxy engine
        proxied_url = encode_payload(stream_url, BASE_URL)

        hls_sources = [{
            "url": proxied_url,
            "file": proxied_url,
            "isM3U8": True,
            "quality": "default",
            "label": "Default"
        }]

        return {
            "sources": [{"file": proxied_url, "url": proxied_url, "quality": "default"}],
            "tracks": [],
            "intro": None,
            "outro": None,
            "headers": {"Referer": BASE_URL},
            "provider": "anikoto",
            "download": "",
            "embed_sources": [],
            "hls_sources": hls_sources,
            "source_type": "hls",
            "available_qualities": ["default"],
            "video_link": proxied_url,
            "source_provider": "anikoto"
        }
