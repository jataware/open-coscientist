"""
Extract clean text from PMC HTML fulltext for agent consumption.

Converts PMC XML/HTML to markdown format, preserving structure while
Removing clutter like references, figure captions, and metadata.
"""

import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def extract_text_from_pmc_html(html_content: str, max_chars: int = 200_000) -> str:
    """
    Convert PMC HTML fulltext to clean markdown.

    Preserves:
    - section headings (abstract, introduction, methods, results, discussion)
    - paragraphs within sections
    - key structure for agent readability

    Removes:
    - XML/HTML tags
    - references section (citation clutter)
    - author affiliations and metadata
    - figure/table captions (images not useful in text)
    - acknowledgments and funding

    args:
        html_content: raw PMC HTML/XML content
        max_chars: maximum characters to return (truncate if exceeded)

    returns:
        markdown-formatted text ready for LLM consumption
    """
    try:
        soup = BeautifulSoup(html_content, 'lxml-xml')

        # remove sections we don't need
        for tag in soup.find_all(['back', 'ref-list', 'ack', 'fn-group', 'fig', 'table-wrap']):
            tag.decompose()

        # extract abstract
        abstract_text = ""
        abstract = soup.find('abstract')
        if abstract:
            paragraphs = abstract.find_all('p')
            if paragraphs:
                abstract_text = '\n\n'.join(p.get_text(strip=True) for p in paragraphs)
            else:
                # sometimes abstract is just text without paragraphs
                abstract_text = abstract.get_text(strip=True)

        # extract main body sections
        sections = []
        body = soup.find('body')
        if body:
            for section in body.find_all('sec', recursive=True):
                # get section heading
                heading = section.find(['title', 'label'])
                heading_text = heading.get_text(strip=True) if heading else "section"

                # skip nested sections (we'll get them separately)
                # only process top-level sections
                if section.parent.name != 'sec':
                    # get direct paragraphs only (not from nested sections)
                    paragraphs = []
                    for p in section.find_all('p', recursive=False):
                        text = p.get_text(strip=True)
                        if text:
                            paragraphs.append(text)

                    # also check for paragraphs in direct children that aren't sections
                    for child in section.children:
                        if hasattr(child, 'name') and child.name not in ['sec', 'title', 'label']:
                            for p in child.find_all('p'):
                                text = p.get_text(strip=True)
                                if text:
                                    paragraphs.append(text)

                    if paragraphs:
                        content = '\n\n'.join(paragraphs)
                        sections.append(f"## {heading_text}\n\n{content}")

        # combine abstract and body
        parts = []
        if abstract_text:
            parts.append(f"# abstract\n\n{abstract_text}")

        parts.extend(sections)

        markdown = '\n\n'.join(parts)

        # truncate if too long
        if len(markdown) > max_chars:
            logger.info(f"Truncating extracted text from {len(markdown)} to {max_chars} chars")
            markdown = markdown[:max_chars] + "\n\n[... truncated for length ...]"

        return markdown

    except Exception as e:
        logger.error(f"Failed to extract text from PMC HTML: {e}")
        # fallback: return raw text extraction
        try:
            soup = BeautifulSoup(html_content, 'lxml-xml')
            text = soup.get_text(separator='\n', strip=True)
            if len(text) > max_chars:
                text = text[:max_chars] + "\n\n[... truncated for length ...]"
            return text
        except Exception as fallback_error:
            logger.error(f"Fallback text extraction also failed: {fallback_error}")
            return "[error: could not extract text from HTML]"
