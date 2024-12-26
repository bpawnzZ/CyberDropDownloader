from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup
from yarl import URL

from cyberdrop_dl.utils.logger import log
from .xenforo_crawler import XenforoCrawler

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


class SimpCityCrawler(XenforoCrawler):
    primary_base_domain = URL("https://simpcity.su")
    login_required = False
    domain = "simpcity"

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, self.domain, "SimpCity")
        # Reduce request rate to respect site's rate limits
        self.request_limiter = AsyncLimiter(5, 2)  # 5 requests per 2 seconds

    async def try_login(self) -> None:
        """
        Custom login handling for SimpCity with more flexible authentication
        """
        # Check if user has provided an email or cookie
        forums_auth_data = self.manager.config_manager.authentication_data.forums
        email = getattr(forums_auth_data, f"{self.domain}_email", None)
        session_cookie = getattr(forums_auth_data, f"{self.domain}_xf_user_cookie", None)

        if session_cookie:
            # If a session cookie is provided, use it
            self.logged_in = True
            return

        if email:
            # If an email is provided, log a message about whitelisting
            log(f"Note: Ensure your email '{email}' is whitelisted on SimpCity", 30)
            self.logged_in = True
            return

        # If no authentication is provided, attempt to scrape without login
        log("Attempting to scrape SimpCity without authentication", 30)
        self.logged_in = True

    async def thread_pager(self, scrape_item: ScrapeItem):
        """
        Custom thread pager to handle potential DDOS-Guard or rate limiting
        """
        page_url = scrape_item.url
        retry_count = 0
        max_retries = 3

        while True:
            try:
                async with self.request_limiter:
                    soup: BeautifulSoup = await self.client.get_soup(
                        self.domain, 
                        page_url, 
                        origin=scrape_item,
                        # Add custom headers to mimic browser
                        headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                            "Accept-Language": "en-US,en;q=0.5",
                            "Referer": str(self.primary_base_domain),
                        }
                    )
                
                next_page = soup.select_one(self.selectors.next_page.element)
                yield soup
                
                if next_page:
                    page_url = next_page.get(self.selectors.next_page.attribute)
                    if page_url:
                        if page_url.startswith("/"):
                            page_url = self.primary_base_domain / page_url[1:]
                        page_url = URL(page_url)
                        log(f"scraping page: {page_url}")
                        retry_count = 0  # Reset retry count on successful page load
                        continue
                break

            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    log(f"Failed to scrape page after {max_retries} attempts: {e}", 40)
                    break
                
                # Wait a bit before retrying
                await asyncio.sleep(2 ** retry_count)
