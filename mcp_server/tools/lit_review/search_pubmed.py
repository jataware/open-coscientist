"""
PubMed literature search tool using Bio.Entrez.
"""

import json
import logging
import os
import ssl
import traceback
from time import sleep
from typing import List, Optional
from urllib.error import HTTPError, URLError

from Bio import Entrez

from mcp_server.models import Article

logger = logging.getLogger(__name__)


_entrez_initialized = False

def _initialize_entrez():
    """
    Initialize Entrez with email and API key from environment.
    Only logs warnings once on first call.
    """
    global _entrez_initialized

    if _entrez_initialized:
        return

    _entrez_initialized = True
    ssl_verify = os.environ.get("DISABLE_SSL_VERIFY", "").lower() in ("true", "1", "yes")
    logger.debug(f"SSL verification: {ssl_verify}")

    if not Entrez.email:
        entrez_email = os.environ.get("ENTREZ_EMAIL")
        if entrez_email:
            Entrez.email = entrez_email
            logger.info(f"Initialized Entrez with email: {entrez_email}")
        else:
            logger.warning("ENTREZ_EMAIL not set - PubMed may have stricter rate limits")

    if not Entrez.api_key:
        entrez_key = os.environ.get("ENTREZ_API_KEY")
        if entrez_key:
            Entrez.api_key = entrez_key
            logger.info("Initialized Entrez with API key")
        else:
            logger.info("ENTREZ_API_KEY not set - using default rate limits")

    if not ssl_verify:
        ssl._create_default_https_context = ssl._create_unverified_context


def check_pubmed_available() -> str:
    """
    Check if PubMed is available by making a test query.

    Returns:
        "true" if PubMed can be accessed successfully, "false" otherwise
    """
    _initialize_entrez()

    entrez_email = os.environ.get("ENTREZ_EMAIL")
    if not entrez_email:
        logger.warning("PubMed unavailable: ENTREZ_EMAIL not set (recommended by NCBI)")
        return "false"

    try:
        logger.debug("Testing PubMed availability with test query...")

        test_results = _entrez_read(Entrez.esearch(db="pubmed", term="cancer", retmax=1))

        id_list = test_results.get("IdList", [])
        if id_list:
            logger.info("PubMed test query successful - PubMed is available")
            return "true"
        else:
            logger.warning("PubMed test query returned no results - might be unavailable")
            logger.debug(f"PubMed test query results: {test_results}")
            return "false"

    except HTTPError as e:
        logger.error(f"PubMed test query failed: HTTP {e.code} {e.reason}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.debug(f"Request URL: {getattr(e, 'url', 'N/A')}")
        logger.debug(f"Response headers: {dict(getattr(e, 'headers', {}))}")
        
        # Try to read error response body
        try:
            if hasattr(e, 'read'):
                error_body = e.read()
                if isinstance(error_body, bytes):
                    error_body = error_body.decode('utf-8', errors='ignore')
                logger.debug(f"Error response body: {error_body[:500]}")
        except Exception:
            pass
        
        logger.debug(f"Full traceback:\n{traceback.format_exc()}")
        logger.warning("PubMed is unavailable - skipping PubMed literature review")
        return "false"
        
    except URLError as e:
        logger.error(f"PubMed test query failed: URL error - {e.reason if hasattr(e, 'reason') else e}")
        logger.error(f"Error type: {type(e).__name__}")
        if hasattr(e, 'url'):
            logger.debug(f"Request URL: {e.url}")
        logger.debug(f"Full traceback:\n{traceback.format_exc()}")
        logger.warning("PubMed is unavailable - skipping PubMed literature review")
        return "false"
        
    except Exception as e:
        logger.error(f"PubMed test query failed: {type(e).__name__}: {e}")
        logger.debug(f"Full traceback:\n{traceback.format_exc()}")
        
        # Log Entrez configuration state
        logger.debug(f"Entrez.email set: {bool(Entrez.email)}")
        logger.debug(f"Entrez.api_key set: {bool(Entrez.api_key)}")
        
        logger.warning("PubMed is unavailable - skipping PubMed literature review")
        return "false"


def _entrez_read(handle) -> dict:
    """Read Entrez response with rate limiting."""
    sleep(0.25)
    
    try:
        results = Entrez.read(handle)
        handle.close()
        return results
    except HTTPError as e:
        # Log HTTP error details
        logger.error(f"Entrez HTTP error ({type(e).__name__}): {e.code} {e.reason}")
        if hasattr(e, 'url'):
            logger.debug(f"Request URL: {e.url}")
        if hasattr(e, 'headers'):
            logger.debug(f"Response headers: {dict(e.headers)}")
        
        # Try to read error response body from the exception
        try:
            if hasattr(e, 'read'):
                error_body = e.read()
                if isinstance(error_body, bytes):
                    error_body = error_body.decode('utf-8', errors='ignore')
                logger.debug(f"Error response body: {error_body[:1000]}")
        except Exception as read_err:
            logger.debug(f"Could not read error response body: {read_err}")
        
        handle.close()
        raise
    except URLError as e:
        logger.error(f"Entrez URL error ({type(e).__name__}): {e.reason if hasattr(e, 'reason') else e}")
        if hasattr(e, 'url'):
            logger.debug(f"Request URL: {e.url}")
        handle.close()
        raise
    except Exception as e:
        logger.error(f"Entrez read error ({type(e).__name__}): {e}")
        
        # Try to read raw response from handle if possible
        try:
            if hasattr(handle, 'read'):
                raw_response = handle.read()
                if isinstance(raw_response, bytes):
                    raw_response = raw_response.decode('utf-8', errors='ignore')
                logger.debug(f"Raw response from handle (first 1000 chars): {raw_response[:1000]}")
        except Exception:
            pass
        
        logger.debug(f"Full traceback:\n{traceback.format_exc()}")
        handle.close()
        raise


def search_pubmed(query: str, max_papers: int = 10) -> str:
    """
    Search PubMed for papers and return Article objects with metadata.

    Args:
        query: search query for PubMed
        max_papers: maximum number of papers to retrieve

    Returns:
        JSON string with list of articles (for LLM agent consumption)
    """
    _initialize_entrez()

    logger.info(f"Searching PubMed with query: '{query}' (max {max_papers} papers)")

    try:
        results = _entrez_read(Entrez.esearch(db="pubmed", term=query, retmax=max_papers))
        id_list = results.get("IdList", [])

        if not id_list:
            logger.warning(f"No results found for query: {query}")
            return json.dumps({"results": [], "count": 0})

        logger.info(f"Found {len(id_list)} papers, fetching metadata...")

        articles = []
        for paper_id in id_list:
            try:
                paper_results = _entrez_read(Entrez.efetch(db="pubmed", id=paper_id))

                pubmed_article = paper_results["PubmedArticle"][0]
                medline = pubmed_article["MedlineCitation"]
                article_data = medline["Article"]

                title = article_data.get("ArticleTitle", "Unknown")

                try:
                    abstract_parts = article_data.get("Abstract", {}).get("AbstractText", [])
                    abstract = " ".join(str(part) for part in abstract_parts) if abstract_parts else None
                except (KeyError, TypeError):
                    abstract = None

                authors = []
                try:
                    author_list = article_data.get("AuthorList", [])
                    for author in author_list:
                        if isinstance(author, dict):
                            first_name = author.get("ForeName", "")
                            last_name = author.get("LastName", "")
                            if first_name and last_name:
                                authors.append(f"{first_name} {last_name}")
                except (KeyError, TypeError):
                    pass

                doi = None
                try:
                    article_ids = pubmed_article.get("PubmedData", {}).get("ArticleIdList", [])
                    for article_id in article_ids:
                        if hasattr(article_id, "attributes") and article_id.attributes.get("IdType") == "doi":
                            doi = str(article_id)
                            break
                except (KeyError, TypeError, AttributeError):
                    pass

                venue = None
                year = None
                try:
                    journal_info = article_data.get("Journal", {})
                    venue = journal_info.get("Title")

                    pub_date = journal_info.get("JournalIssue", {}).get("PubDate", {})
                    year_str = pub_date.get("Year")
                    if year_str:
                        year = int(year_str)
                except (KeyError, TypeError, ValueError):
                    pass

                url = f"https://pubmed.ncbi.nlm.nih.gov/{paper_id}/"
                if doi:
                    url = f"https://doi.org/{doi}"

                article = Article(
                    title=title,
                    url=url,
                    authors=authors,
                    year=year,
                    venue=venue,
                    abstract=abstract,
                    source_id=paper_id,
                    source="pubmed"
                )

                articles.append(article)
                logger.debug(f"fetched metadata for paper {paper_id}: {title[:50]}...")

            except Exception as e:
                logger.warning(f"Failed to fetch metadata for paper {paper_id}: {e}")
                continue

        logger.info(f"Successfully retrieved {len(articles)} papers from PubMed")

        articles_json = [article.to_dict() for article in articles]
        return json.dumps({"results": articles_json, "count": len(articles)})

    except Exception as e:
        logger.error(f"Error searching PubMed: {e}")
        return json.dumps({"error": str(e), "results": [], "count": 0})


def search_pubmed_raw(query: str, max_papers: int = 10) -> List[Article]:
    """
    Search PubMed and return Article objects (for direct API usage, not agent).

    Args:
        query: search query for PubMed
        max_papers: maximum number of papers to retrieve

    Returns:
        list of Article objects with title, abstract, authors, DOI, etc.
    """
    _initialize_entrez()

    logger.info(f"Searching PubMed with query: '{query}' (max {max_papers} papers)")

    try:
        results = _entrez_read(Entrez.esearch(db="pubmed", term=query, retmax=max_papers))
        id_list = results.get("IdList", [])

        if not id_list:
            logger.warning(f"No results found for query: {query}")
            return []

        logger.info(f"Found {len(id_list)} papers, fetching metadata...")

        articles = []
        for paper_id in id_list:
            try:
                paper_results = _entrez_read(Entrez.efetch(db="pubmed", id=paper_id))

                pubmed_article = paper_results["PubmedArticle"][0]
                medline = pubmed_article["MedlineCitation"]
                article_data = medline["Article"]

                title = article_data.get("ArticleTitle", "Unknown")

                try:
                    abstract_parts = article_data.get("Abstract", {}).get("AbstractText", [])
                    abstract = " ".join(str(part) for part in abstract_parts) if abstract_parts else None
                except (KeyError, TypeError):
                    abstract = None

                authors = []
                try:
                    author_list = article_data.get("AuthorList", [])
                    for author in author_list:
                        if isinstance(author, dict):
                            first_name = author.get("ForeName", "")
                            last_name = author.get("LastName", "")
                            if first_name and last_name:
                                authors.append(f"{first_name} {last_name}")
                except (KeyError, TypeError):
                    pass

                doi = None
                try:
                    article_ids = pubmed_article.get("PubmedData", {}).get("ArticleIdList", [])
                    for article_id in article_ids:
                        if hasattr(article_id, "attributes") and article_id.attributes.get("IdType") == "doi":
                            doi = str(article_id)
                            break
                except (KeyError, TypeError, AttributeError):
                    pass

                venue = None
                year = None
                try:
                    journal_info = article_data.get("Journal", {})
                    venue = journal_info.get("Title")

                    pub_date = journal_info.get("JournalIssue", {}).get("PubDate", {})
                    year_str = pub_date.get("Year")
                    if year_str:
                        year = int(year_str)
                except (KeyError, TypeError, ValueError):
                    pass

                url = f"https://pubmed.ncbi.nlm.nih.gov/{paper_id}/"
                if doi:
                    url = f"https://doi.org/{doi}"

                article = Article(
                    title=title,
                    url=url,
                    authors=authors,
                    year=year,
                    venue=venue,
                    abstract=abstract,
                    source_id=paper_id,
                    source="pubmed"
                )

                articles.append(article)
                logger.debug(f"fetched metadata for paper {paper_id}: {title[:50]}...")

            except Exception as e:
                logger.warning(f"Failed to fetch metadata for paper {paper_id}: {e}")
                continue

        logger.info(f"Successfully retrieved {len(articles)} papers from PubMed")
        return articles

    except Exception as e:
        logger.error(f"Error searching PubMed: {e}")
        raise
