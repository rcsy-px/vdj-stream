import logging
from urllib.parse import quote_plus

from playwright.async_api import Browser, Playwright, async_playwright

from ..models import TrackSearchResult
from .base import SearchProvider, duration_to_seconds, youtube_thumbnail_url

logger = logging.getLogger(__name__)

EXTRACT_RESULTS_JS = r"""
() => {
  const anchors = Array.from(document.querySelectorAll('a[href*="/watch?v="]'));
  const items = [];
  for (const a of anchors) {
    try {
      const url = new URL(a.href);
      const videoId = url.searchParams.get("v");
      if (!videoId) continue;
      const root = a.closest("ytd-video-renderer") ||
        a.closest("ytd-rich-item-renderer") ||
        a.closest("ytd-compact-video-renderer") ||
        a.closest("ytd-grid-video-renderer") || a.parentElement;
      const titleEl = root?.querySelector("#video-title") ||
        root?.querySelector("a#video-title") ||
        root?.querySelector("yt-formatted-string#video-title") || a;
      const title = (titleEl?.getAttribute("title") ||
        titleEl?.textContent || a.textContent || "").trim();
      const channelEl = root?.querySelector("ytd-channel-name a") ||
        root?.querySelector("#channel-name a") ||
        root?.querySelector("a[href^='/@']");
      const imgEl = root?.querySelector("img");
      const durationCandidates = Array.from(root?.querySelectorAll(
        "ytd-thumbnail-overlay-time-status-renderer, " +
        "yt-thumbnail-overlay-badge-view-model, " +
        ".badge-shape-wiz__text, .yt-badge-shape__text"
      ) || []);
      let durationText = null;
      for (const candidate of durationCandidates) {
        const text = (candidate.textContent || "").replace(/\s+/g, " ").trim();
        const match = text.match(/\b\d{1,2}:\d{2}(?::\d{2})?\b/);
        if (match) {
          durationText = match[0];
          break;
        }
      }
      items.push({
        videoId, title,
        channelName: (channelEl?.textContent || "").trim() || null,
        channelUrl: channelEl?.href || null,
        thumbnailUrl: imgEl?.src || imgEl?.getAttribute("data-thumb") || null,
        durationText
      });
    } catch (_) {}
  }
  return items;
}
"""


class ChromiumYouTubeSearchProvider(SearchProvider):
    name = "youtube_browser"

    def __init__(self, headless: bool = True, timeout_seconds: float = 20):
        self.headless = headless
        self.timeout_ms = int(timeout_seconds * 1000)
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    async def _ensure_browser(self) -> Browser:
        if self._browser and self._browser.is_connected():
            return self._browser
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=["--autoplay-policy=user-gesture-required", "--mute-audio"],
        )
        return self._browser

    async def search(self, query: str, limit: int) -> list[TrackSearchResult]:
        browser = await self._ensure_browser()
        page = await browser.new_page()
        try:
            await page.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in {"media", "font"}
                else route.continue_(),
            )
            await page.goto(
                f"https://www.youtube.com/results?search_query={quote_plus(query)}",
                wait_until="domcontentloaded",
                timeout=self.timeout_ms,
            )
            await page.wait_for_selector('a[href*="/watch?v="]', timeout=self.timeout_ms)
            raw_results = await page.evaluate(EXTRACT_RESULTS_JS)
        finally:
            await page.close()

        results: list[TrackSearchResult] = []
        seen: set[str] = set()
        for item in raw_results:
            video_id = item.get("videoId", "")
            title = item.get("title", "").strip()
            if not video_id or video_id in seen or not title:
                continue
            seen.add(video_id)
            duration = item.get("durationText")
            results.append(
                TrackSearchResult(
                    id=f"youtube:{video_id}",
                    provider=self.name,
                    videoId=video_id,
                    title=title,
                    channelName=item.get("channelName"),
                    channelUrl=item.get("channelUrl"),
                    durationText=duration,
                    durationSeconds=duration_to_seconds(duration),
                    thumbnailUrl=item.get("thumbnailUrl") or youtube_thumbnail_url(video_id),
                    watchUrl=f"https://www.youtube.com/watch?v={video_id}",
                    badges=["youtube-browser"],
                )
            )
            if len(results) >= limit:
                break
        logger.info("Chromium search returned %s results", len(results))
        return results

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._browser = None
        self._playwright = None
