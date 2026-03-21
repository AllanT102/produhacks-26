"""Playwright browser singleton. All tools share this single Chrome instance."""

import asyncio
import threading


class _BrowserManager:
    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        asyncio.run_coroutine_threadsafe(self._start(), self._loop).result(timeout=30)

    async def _start(self):
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            channel="chrome",
            headless=False,
            args=["--start-maximized"],
        )
        self._context = await self._browser.new_context(no_viewport=True)
        self._page = await self._context.new_page()

    def run(self, coro):
        """Block the calling thread until the coroutine completes on the browser loop."""
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    @property
    def page(self):
        return self._page

    @property
    def context(self):
        return self._context

    def shutdown(self):
        try:
            asyncio.run_coroutine_threadsafe(self._browser.close(), self._loop).result(timeout=5)
        except Exception:
            pass
        try:
            asyncio.run_coroutine_threadsafe(self._pw.stop(), self._loop).result(timeout=5)
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)


_manager: _BrowserManager | None = None
_manager_lock = threading.Lock()


def get_manager() -> _BrowserManager:
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = _BrowserManager()
    return _manager
