import time
from urllib.parse import urlparse

import aiohttp
from langchain_community.document_loaders import AsyncHtmlLoader
from langchain_community.document_transformers.html2text import Html2TextTransformer
from loguru import logger

from llm_engineering.domain.documents import ArticleDocument

from .base import BaseCrawler

_HEADER_TEMPLATE = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
_MAX_RETRIES = 3
_RETRY_DELAY_SECONDS = 10


class CustomArticleCrawler(BaseCrawler):
    model = ArticleDocument

    def __init__(self) -> None:
        super().__init__()

    def extract(self, link: str, **kwargs) -> None:
        old_model = self.model.find(link=link)
        if old_model is not None:
            logger.info(f"Article already exists in the database: {link}")

            return

        logger.info(f"Starting scrapping article: {link}")

        docs = self._load_with_retries(link)

        html2text = Html2TextTransformer()
        docs_transformed = html2text.transform_documents(docs)
        doc_transformed = docs_transformed[0]

        content = {
            "Title": doc_transformed.metadata.get("title"),
            "Subtitle": doc_transformed.metadata.get("description"),
            "Content": doc_transformed.page_content,
            "language": doc_transformed.metadata.get("language"),
        }

        parsed_url = urlparse(link)
        platform = parsed_url.netloc

        user = kwargs["user"]
        instance = self.model(
            content=content,
            link=link,
            platform=platform,
            author_id=user.id,
            author_full_name=user.full_name,
        )
        instance.save()

        logger.info(f"Finished scrapping custom article: {link}")

    def _load_with_retries(self, link: str) -> list:
        for attempt in range(1, _MAX_RETRIES + 1):
            loader = AsyncHtmlLoader([link], header_template=_HEADER_TEMPLATE, raise_for_status=True)
            try:
                return loader.load()
            except aiohttp.ClientResponseError as e:
                if e.status == 429 and attempt < _MAX_RETRIES:
                    logger.warning(
                        f"Rate limited (429) while scraping {link}. "
                        f"Retrying in {_RETRY_DELAY_SECONDS}s (attempt {attempt}/{_MAX_RETRIES})."
                    )
                    time.sleep(_RETRY_DELAY_SECONDS)
                else:
                    raise

        raise RuntimeError(f"Failed to load {link} after {_MAX_RETRIES} attempts.")
