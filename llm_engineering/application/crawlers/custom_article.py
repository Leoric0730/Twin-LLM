from urllib.parse import urlparse

import httpx
from langchain_community.document_transformers.html2text import Html2TextTransformer
from loguru import logger

from llm_engineering.domain.documents import ArticleDocument

from .base import BaseCrawler


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

        html_content = None
        
        try:
            # First attempt with SOCKS proxy
            socks_proxy = "socks5://127.0.0.1:7890"
            with httpx.Client(proxy=socks_proxy, timeout=30) as client:
                response = client.get(link)
                response.raise_for_status()
                html_content = response.text
                logger.info(f"Successfully fetched article using SOCKS proxy: {link}")
        except Exception as e:
            logger.warning(f"Failed to fetch with SOCKS proxy: {e}. Trying HTTP proxy...")
            
            try:
                # Second attempt with HTTP proxy
                http_proxy = "http://127.0.0.1:7890"
                with httpx.Client(proxy=http_proxy, timeout=30) as client:
                    response = client.get(link)
                    response.raise_for_status()
                    html_content = response.text
                    logger.info(f"Successfully fetched article using HTTP proxy: {link}")
            except Exception as e:
                logger.warning(f"Failed to fetch with HTTP proxy: {e}. Trying without proxy...")
                
                try:
                    # Third attempt without proxy
                    with httpx.Client(timeout=30) as client:
                        response = client.get(link)
                        response.raise_for_status()
                        html_content = response.text
                        logger.info(f"Successfully fetched article without proxy: {link}")
                except Exception as e:
                    logger.error(f"All attempts failed to fetch article: {e}")
                    raise

        html2text = Html2TextTransformer()
        
        # Create a dummy Document object for the transformer
        from langchain_core.documents import Document
        doc = Document(page_content=html_content, metadata={"source": link})
        
        docs_transformed = html2text.transform_documents([doc])
        doc_transformed = docs_transformed[0]

        content = {
            "Title": doc_transformed.metadata.get("title", "N/A"),
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
