#!/usr/bin/env python3
"""Thin shim — v2 code lives in web_crawl/ package."""

from web_crawl import (  # noqa: F401
    WebsiteCloner,
    clone_website_job,
    clone_website,
    main,
)

if __name__ == "__main__":
    main()
