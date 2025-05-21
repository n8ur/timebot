#!/usr/bin/env python3
# /usr/local/lib/timebot/bin/web2rag.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

# -*- coding: utf-8 -*-

import os
import argparse
import re
import time
import datetime
import logging
from urllib.parse import urlparse, urljoin, urldefrag, parse_qs
from collections import deque
from playwright.sync_api import sync_playwright, Error as PlaywrightError
from bs4 import BeautifulSoup, Tag # Import Tag for type checking if needed
from markdownify import markdownify

# Configure logging (level will be overridden by command-line arg)
logging.basicConfig(
    level=logging.WARN, # Initial level
    format="%(asctime)s - %(levelname)s - %(threadName)s - %(message)s",
)
# Keep Playwright/urllib3 logs less verbose
logging.getLogger("playwright").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)


# Define common binary/non-HTML file extensions to exclude
BINARY_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".ico",
    ".ps",
    ".zip", ".rar", ".tar", ".gz", ".bz2", ".7z", ".deb", ".ddeb", ".tgz",
    ".xz", ".gzip",
    ".mp3", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".wav", ".ogg", ".mkv",
    ".m4v", ".mpg",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp",
    ".exe", ".dmg", ".iso", ".bin", ".msi", ".dll",
    ".css", ".js",
    ".dat", ".tim",    # leave out phase/freq/data even if ascii-like
    ".prn", ".agr", "s1p", ".sta", ".sch", ".brd",
    ".bak",
}


# --- Helper Functions ---

def is_binary_url(normalized_url):
    """Check if a NORMALIZED URL likely points to a binary file based on extension."""
    try:
        path = urlparse(normalized_url).path
        if not path: return False
        # Ensure path is treated case-insensitively for extension check
        return any(path.lower().endswith(ext) for ext in BINARY_EXTENSIONS)
    except Exception: return False

def sanitize_filename(normalized_url):
    """Creates a safe filename from a NORMALIZED URL (query params kept)."""
    try:
        parsed_url = urlparse(normalized_url)
        path = parsed_url.path
        query = parsed_url.query # Keep query for filename uniqueness
        # Ensure netloc exists before replacing
        domain_part = parsed_url.netloc.replace(".", "_") if parsed_url.netloc else "local"

        # Handle root, index paths, and regular paths
        if not path or path == "/" or path.endswith("/"):
            # Use 'index' for root or paths ending in /
            if path in ["/", ""]:
                filename_base = f"{domain_part}_index"
            else:
                # Remove trailing slash before replacing internal slashes
                filename_base = f"{domain_part}_{path.strip('/')}_index".replace("/", "_")
        else:
            # Path doesn't end in /, treat as file or directory name part
            filename_base = f"{domain_part}_{path.strip('/')}".replace("/", "_")

        # Handle query parameters safely
        if query:
            # Filter out potentially problematic query params like Apache index sorting
            query_parts = [qp for qp in query.split('&') if not qp.startswith('C=') and not qp.startswith('O=')]
            if query_parts:
                filtered_query = "&".join(query_parts)
                # Sanitize query part more aggressively
                query_part = re.sub(r"[^a-zA-Z0-9_-]", "_", filtered_query)
                # Limit length of query part in filename
                filename_base += "_q_" + query_part[:50]

        # General sanitization for the whole base name
        filename = re.sub(r"[^a-zA-Z0-9_.-]", "", filename_base) # Allow dots and hyphens
        filename = re.sub(r'_{2,}', '_', filename) # Collapse multiple underscores
        filename = filename.strip('_.-') # Remove leading/trailing unwanted chars

        # Ensure filename is not excessively long
        max_len = 150
        if len(filename) > max_len:
            filename = filename[:max_len]

        # Handle cases where sanitization results in empty filename
        if not filename:
            filename = domain_part or "page" # Fallback to domain or generic 'page'

        return f"{filename}.md"
    except Exception as e:
        logging.error(f"Error sanitizing URL '{normalized_url}': {e}")
        # Provide a unique fallback filename in case of error
        return f"error_filename_{int(time.time())}.md"


def get_domain(url):
    """Extracts the netloc (domain) from a URL."""
    try:
        return urlparse(url).netloc
    except Exception as e:
        logging.warning(f"Could not parse domain from URL '{url}': {e}")
        return None

def normalize_url(url):
    """Removes fragment, trailing slash, ensures scheme, KEEPS query params,
       and removes 'www.' prefix from domain."""
    try:
        if not isinstance(url, str): return None
        # Handle scheme-relative URLs
        if url.startswith('//'): url = 'https:' + url # Default to https

        # Remove fragment first
        url_no_frag = urldefrag(url).url
        parsed = urlparse(url_no_frag)

        # Ensure scheme exists, default to https
        scheme = parsed.scheme or 'https'
        if not parsed.scheme and parsed.netloc: # If netloc exists but scheme doesn't, add default
             url_no_frag = f"{scheme}://{url_no_frag}"
             parsed = urlparse(url_no_frag) # Re-parse with scheme

        # Handle URLs that might be just paths or have scheme but no domain
        if not parsed.netloc:
             # If it looks like a path relative to root, return as is (cannot normalize further)
             if url_no_frag.startswith('/'): return url_no_frag
             # Log warning if scheme exists without netloc (e.g., "http:/pages")
             if parsed.scheme:
                 logging.warning(f"URL '{url}' has scheme but no netloc, cannot normalize reliably.")
             # Attempt a basic cleanup for other cases (e.g., just "page.html")
             try:
                 # Remove query/fragment, strip trailing slash if it's just a path
                 return urlparse(url_no_frag)._replace(query=None, fragment=None).geturl().rstrip('/')
             except Exception:
                 return url_no_frag.rstrip('/') # Fallback

        # Normalize 'www.' prefix
        netloc = parsed.netloc
        if netloc.lower().startswith('www.'):
            netloc = netloc[4:] # Remove 'www.'

        # Normalize path: ensure leading slash, remove trailing slash unless root
        path = parsed.path
        if not path:
            path = '/'
        else:
            if not path.startswith('/'): path = '/' + path # Ensure leading slash
            if path != '/' and path.endswith('/'): path = path[:-1] # Remove trailing slash if not root

        # Reconstruct the normalized URL
        normalized = f"{scheme}://{netloc}{path}"
        if parsed.query: normalized += f"?{parsed.query}" # Keep query parameters

        return normalized
    except Exception as e:
        logging.warning(f"Could not normalize URL '{url}': {e}")
        # Fallback: remove fragment and trailing slash only
        return urldefrag(url).url.rstrip('/')


# --- Main Crawler Class using Playwright ---

class PlaywrightCrawler:
    """
    Crawls a website starting from a URL, extracts content, converts to Markdown,
    and saves each page, following links within allowed domains and filtering common non-content URLs.
    Restricts crawl to the starting path if one is provided.
    Saves files into a subdirectory within the base_dir named after the primary domain.
    """

    def __init__(self, start_url, max_pages, base_dir, include_metadata=True, user_agent=None, content_selector=None, headless=True, extra_domain=None):
        """Initializes the crawler."""
        self.start_url_original = start_url
        self.start_url_normalized = normalize_url(start_url)
        if not self.start_url_normalized or not urlparse(self.start_url_normalized).scheme:
             raise ValueError(f"Could not normalize start URL or scheme missing: {start_url}")

        self.allowed_domain = get_domain(self.start_url_normalized)
        if not self.allowed_domain:
            raise ValueError(f"Could not parse domain from start URL: {start_url}")

        self.extra_allowed_domain = extra_domain

        # --- Path Restriction Logic ---
        parsed_start = urlparse(self.start_url_normalized)
        self.start_path = parsed_start.path if parsed_start.path else "/"

        # Ensure start path ends with / if it's not a file-like path and not root
        if self.start_path != '/' and '.' not in self.start_path.split('/')[-1] and not self.start_path.endswith('/'):
             self.start_path += '/'
        logging.info(f"Path restriction initialized to: '{self.start_path}'")
        # --- End Path Restriction Logic ---

        self.max_pages = max_pages
        self.base_dir = base_dir # Store base directory
        self.include_metadata = include_metadata
        self.user_agent = user_agent
        self.content_selector = content_selector
        self.headless = headless
        self.urls_to_visit = deque([self.start_url_normalized])
        self.visited_urls = set()
        self.processed_count = 0

        # --- Create Domain-and-Path-Specific Output Directory ---
        # 1.  Sanitize the domain name for use as a directory name
        sanitized_domain = re.sub(r"[^a-zA-Z0-9_-]", "_", self.allowed_domain)
        sanitized_domain = sanitized_domain.strip('_.-') # Clean leading/trailing
        if not sanitized_domain: sanitized_domain = "unknown_domain" # Fallback

        # 2. Sanitize the starting path for directory naming
        #    Use the path from the *parsed* start URL.
        path_for_dir = parsed_start.path if parsed_start.path else "/"
        # If the path looks like a file, use its directory part
        last_segment = path_for_dir.split('/')[-1]
        if '.' in last_segment and path_for_dir != '/': # Check it's not just root
             dir_path_component = os.path.dirname(path_for_dir)
        else:
             dir_path_component = path_for_dir

        # Clean up the path component of the directory name
        sanitized_path_component = dir_path_component.strip('/') # Remove leading/trailing slashes
        if sanitized_path_component: # Only process if path wasn't just '/'
            sanitized_path_component = sanitized_path_component.replace('/', '_') # Replace internal slashes
            sanitized_path_component = re.sub(r"[^a-zA-Z0-9_-]", "_", sanitized_path_component) # General sanitize
            sanitized_path_component = re.sub(r'_{2,}', '_', sanitized_path_component) # Collapse underscores
            sanitized_path_component = sanitized_path_component.strip('_.-') # Final cleanup

        # 3. Combine domain and path (if path component exists)
        if sanitized_path_component:
            final_dir_name = f"{sanitized_domain}_{sanitized_path_component}"
        else:
            # If start path was root ('/'), just use the domain
            final_dir_name = sanitized_domain

        self.output_dir = os.path.join(self.base_dir, final_dir_name)
        # --- End Output Directory Setup ---

        log_msg = f"Crawler initialized. Start URL: '{start_url}', Normalized Start: '{self.start_url_normalized}', Allowed Primary Domain: '{self.allowed_domain}'"
        if self.extra_allowed_domain: log_msg += f", Extra Allowed: '{self.extra_allowed_domain}'"
        log_msg += f", Restricting to path: '{self.start_path}'"
        log_msg += f", Base Output Dir: '{self.base_dir}', Domain Output Dir: '{self.output_dir}'" # Log new dir structure
        logging.info(log_msg)


    def can_visit(self, normalized_url):
        """
        Checks if a NORMALIZED URL should be visited.
        Includes domain, path restriction, and filter checks.
        """
        # 0. Basic check if URL is valid
        if not normalized_url: return False

        # 1. Already visited?
        if normalized_url in self.visited_urls: return False

        # 2. Binary file?
        if is_binary_url(normalized_url): return False

        # 3. Correct Scheme?
        try:
            parsed_url = urlparse(normalized_url)
            if parsed_url.scheme not in ["http", "https"]: return False
        except Exception:
            logging.warning(f"Could not parse scheme for URL: {normalized_url}")
            return False # Cannot determine scheme

        # 4. Specific Domain Check
        url_domain = parsed_url.netloc
        if not url_domain: return False # Cannot visit if no domain

        is_allowed_domain = (url_domain == self.allowed_domain)
        if self.extra_allowed_domain and url_domain == self.extra_allowed_domain:
            is_allowed_domain = True
        if not is_allowed_domain: return False

        # --- 5. Path Restriction Check ---
        current_path = parsed_url.path if parsed_url.path else "/"
        required_start_path = self.start_path

        # Only apply restriction if start path is meaningful (not just '/')
        if required_start_path and required_start_path != '/':
            # Ensure current_path also ends with / if it's not file-like for comparison
            current_path_for_compare = current_path
            if '.' not in current_path.split('/')[-1] and not current_path.endswith('/'):
                current_path_for_compare += '/'

            # Check if the comparison path starts with the required start path
            if not current_path_for_compare.startswith(required_start_path):
                # logging.info(f"Skipping (path mismatch): Path='{current_path_for_compare}' vs StartPath='{required_start_path}', URL='{normalized_url}'")
                return False
        # --- END Path Restriction Check ---

        # --- 6. Filter out common non-content patterns (using normalized URL) ---
        try:
            query_params = parse_qs(parsed_url.query)
            # Common WP/CMS query params indicating non-primary content
            non_content_params = {'replytocom', 'feed', 'amp', 'paged', 'cat', 'tag', 'author', 'm', 'C', 'O', 'share'}
            if any(key in query_params for key in non_content_params):
                return False
        except Exception: pass # Ignore query parsing errors

        # Common path segments indicating non-primary content
        exclusion_paths = [
            "/page/", "/category/", "/tag/", "/author/", "/feed/", "/search/",
            "/wp-login.php", "/wp-admin/", "/wp-comments-post.php", "/wp-json/",
            "/xmlrpc.php", "/trackback/", "/embed/",
            # Add others as needed
        ]
        path_lower = current_path.lower()
        if any(pattern in path_lower for pattern in exclusion_paths):
             return False

        # Filter out simple date archive paths like /2023/, /2023/05/, /2023/05/10/
        if re.match(r'^/\d{4}(/\d{2}(/\d{2})?)?/?$', path_lower):
             return False
        # -------------------------------------------------

        # If all checks pass
        return True


    def crawl(self):
        """Starts the crawling process using Playwright."""
        # Create the specific output directory (base_dir/sanitized_domain)
        os.makedirs(self.output_dir, exist_ok=True)
        log_msg = f"Starting crawl at {self.start_url_normalized}, Allowed Primary Domain: {self.allowed_domain}"
        if self.extra_allowed_domain: log_msg += f", Extra Allowed: {self.extra_allowed_domain}"
        log_msg += f", Max pages: {self.max_pages}, Path Restriction: '{self.start_path}'"
        logging.info(log_msg)
        logging.info(f"Output directory: {self.output_dir}") # Log the final output dir
        if self.content_selector: logging.info(f"Using content selector: '{self.content_selector}'")

        with sync_playwright() as p:
            browser = None
            context = None
            page = None
            try:
                browser = p.chromium.launch(headless=self.headless)
                context_options = {'ignore_https_errors': True} # Ignore cert errors if needed
                if self.user_agent: context_options['user_agent'] = self.user_agent
                context = browser.new_context(**context_options)
                page = context.new_page()
            except PlaywrightError as e:
                logging.error(f"Failed to launch Playwright browser: {e}")
                return
            except Exception as e:
                logging.error(f"Unexpected error during Playwright setup: {e}")
                return

            while self.urls_to_visit and self.processed_count < self.max_pages:
                current_normalized_url = self.urls_to_visit.popleft()

                # Double check if already visited (might have been added again before processing)
                if current_normalized_url in self.visited_urls:
                     logging.debug(f"Skipping {current_normalized_url} as it was already visited.")
                     continue
                self.visited_urls.add(current_normalized_url)

                logging.info(f"Processing ({self.processed_count + 1}/{self.max_pages}): {current_normalized_url}")
                response = None # Initialize response
                try:
                    # Navigate to the page
                    response = page.goto(current_normalized_url, wait_until='domcontentloaded', timeout=45000)

                    # --- Improved Response Handling ---
                    if response is None:
                        logging.warning(f"Navigation failed for {current_normalized_url}, no response received.")
                        continue # Skip to next URL

                    if not response.ok:
                        # Log based on status code
                        if response.status == 404:
                            logging.warning(f"File not found (404): {current_normalized_url}")
                        elif response.status == 403:
                            logging.warning(f"Forbidden (403): {current_normalized_url}")
                        elif response.status >= 500:
                            logging.error(f"Server error ({response.status}): {current_normalized_url}")
                        else:
                            logging.warning(f"Failed to load page {current_normalized_url}, status: {response.status}")
                        continue # Skip processing this URL
                    # --- End Improved Response Handling ---

                    # --- Process successful response ---
                    html_content = page.content()
                    if not html_content:
                         logging.warning(f"Received empty content for {current_normalized_url}")
                         continue

                    # Call process_page only if content received and response OK
                    self.process_page(current_normalized_url, html_content)
                    self.processed_count += 1
                    # --- End Process successful response ---

                except PlaywrightError as e:
                    # Log Playwright-specific errors (timeouts, navigation errors, etc.)
                    logging.warning(f"Playwright error processing {current_normalized_url}: {e}")
                except Exception as e:
                    # Log other unexpected errors during page processing
                    logging.error(f"Unexpected error processing {current_normalized_url}: {e}", exc_info=True)
                finally:
                    # Add a small delay to avoid overwhelming the server
                    time.sleep(0.5)

            # --- Cleanup ---
            if browser:
                try:
                    if context: context.close() # Close context first
                    browser.close()
                except Exception as e:
                    logging.error(f"Error closing Playwright browser/context: {e}")

            logging.info(f"Crawling finished. Processed {self.processed_count} pages.")
            logging.info(f"Total unique URLs marked as visited: {len(self.visited_urls)}")
            logging.info(f"URLs remaining in queue (if max_pages reached): {len(self.urls_to_visit)}")


    def process_page(self, current_normalized_url, html_content):
        """Parses HTML, extracts links, converts to Markdown, and saves.
           Implements a title extraction hierarchy: <title>, <h1>, <h2>, <h3>, filename.
           Skips saving Apache index pages but still processes links on them.
        """
        try:
            # --- Base URL for joining relative links ---
            base_url_for_joining = current_normalized_url
            parsed_base = urlparse(base_url_for_joining)
            if parsed_base.path and '.' not in parsed_base.path.split('/')[-1] and not base_url_for_joining.endswith('/'):
                 base_url_for_joining += '/'
            # --- End Base URL ---

            soup = BeautifulSoup(html_content, "lxml")

            # --- Check for Apache Index Page ---
            title_tag = soup.find('title') # Find title tag early for reuse
            is_apache_index = title_tag and "Index of /" in title_tag.get_text()

            # --- Generate Filename (needed for fallback title and saving) ---
            filename = sanitize_filename(current_normalized_url)
            filepath = os.path.join(self.output_dir, filename)

            if is_apache_index:
                 logging.info(f"Skipping save for Apache directory index: {current_normalized_url}")
                 # REMOVED 'return' FROM HERE
            else:
                # --- Determine Content Element and Scope for Header Search ---
                html_to_convert = ""
                content_search_scope = None # Where to look for H1/H2/H3
                target_element = None

                if self.content_selector:
                    target_element = soup.select_one(self.content_selector)
                    if target_element:
                        logging.debug(f"Using content from selector '{self.content_selector}' for {current_normalized_url}")
                        html_to_convert = str(target_element)
                        content_search_scope = target_element # Search within selected element
                    else:
                        is_html_file = current_normalized_url.lower().endswith(('.html', '.htm'))
                        log_level = logging.WARNING if is_html_file else logging.INFO
                        logging.log(log_level, f"Content selector '{self.content_selector}' not found on {current_normalized_url}. Falling back to body.")

                # Fallback to body or full HTML if selector fails or isn't specified
                if not html_to_convert:
                    body_tag = soup.find('body')
                    if body_tag:
                        html_to_convert = str(body_tag)
                        if not content_search_scope: # Only set scope if not already set by selector
                            content_search_scope = body_tag
                    else:
                        html_to_convert = html_content # Last resort for conversion content
                        if not content_search_scope: # Last resort scope
                            content_search_scope = soup

                markdown_content = None # Initialize markdown content
                if not html_to_convert:
                    logging.warning(f"No HTML content found to convert for {current_normalized_url}")
                    # Proceed to save metadata even if content is empty/missing
                else:
                    # --- Convert selected HTML to Markdown ---
                    try:
                        strip_tags = ['script', 'style', 'nav', 'footer', 'aside', 'header', 'button', 'form', 'input', 'textarea', 'select', 'option', 'figure', 'figcaption']
                        markdown_content = markdownify(html_to_convert, heading_style="ATX", strip=strip_tags)
                    except Exception as md_err:
                        logging.error(f"Markdownify error on {current_normalized_url}: {md_err}")
                        markdown_content = "[Markdown conversion failed]" # Indicate failure

                    if not markdown_content or markdown_content.isspace():
                        logging.warning(f"Markdown conversion resulted in empty/whitespace content for {current_normalized_url}")
                        # Keep markdown_content as empty/whitespace or failed indicator

                # --- Save Markdown File (only if not Apache index) ---
                try:
                    capture_time = datetime.datetime.now(datetime.timezone.utc)
                    timestamp_str = capture_time.strftime('%Y-%m-%dT%H:%M:%SZ') # ISO 8601

                    with open(filepath, "w", encoding="utf-8") as f:
                        # Add metadata if requested
                        if self.include_metadata:
                            f.write(f"---\n")
                            f.write(f"source_url: {current_normalized_url}\n")

                            # --- Robust Title Extraction Hierarchy ---
                            page_title = ""

                            # 1. Try <title> tag
                            if title_tag:
                                title_text = title_tag.get_text().strip()
                                # Exclude the "Index of /" part from being the title
                                if title_text and "Index of /" not in title_text:
                                    page_title = title_text
                                    logging.debug(f"Title source: <title> tag for {current_normalized_url}")

                            # Helper function to find first header text in scope
                            def find_header_text(scope, tag_name):
                                if not scope: return None
                                if not isinstance(scope, (BeautifulSoup, Tag)):
                                    logging.warning(f"Invalid scope type for header search: {type(scope)}")
                                    return None
                                header_tag = scope.find(tag_name)
                                if header_tag:
                                    header_text = header_tag.get_text().strip()
                                    if header_text:
                                        return header_text
                                return None

                            # 2. Try <h1> if no title yet
                            if not page_title:
                                h1_title = find_header_text(content_search_scope, 'h1')
                                if h1_title:
                                    page_title = h1_title
                                    logging.debug(f"Title source: <h1> tag for {current_normalized_url}")

                            # 3. Try <h2> if no title yet
                            if not page_title:
                                h2_title = find_header_text(content_search_scope, 'h2')
                                if h2_title:
                                    page_title = h2_title
                                    logging.debug(f"Title source: <h2> tag for {current_normalized_url}")

                            # 4. Try <h3> if no title yet
                            if not page_title:
                                h3_title = find_header_text(content_search_scope, 'h3')
                                if h3_title:
                                    page_title = h3_title
                                    logging.debug(f"Title source: <h3> tag for {current_normalized_url}")

                            # 5. Fallback to filename if still no title
                            if not page_title:
                                page_title = filename[:-3] # Remove .md extension
                                logging.debug(f"Title source: Fallback to filename for {current_normalized_url}")

                            # Sanitize and write the final title
                            sanitized_title = page_title.replace('"', "'").replace('\n', ' ').strip()
                            if not sanitized_title:
                                sanitized_title = filename[:-3].replace('"', "'").replace('\n', ' ').strip()
                                logging.warning(f"Title was empty after initial extraction and sanitization, using sanitized filename for {current_normalized_url}")
                            f.write(f"title: \"{sanitized_title}\"\n")
                            # --- End Robust Title Extraction ---

                            f.write(f"captured_at: {timestamp_str}\n")
                            f.write(f"---\n\n")

                        # Write main content
                        f.write(markdown_content.strip() if markdown_content else "")
                    logging.info(f"Saved: {filepath}")
                except IOError as e:
                    logging.error(f"Error writing file {filepath}: {e}")
                except Exception as e:
                    logging.error(f"Unexpected error writing file {filepath}: {e}")
            # --- End Save Block (else block for not is_apache_index) ---

            # --- Link Processing (runs for ALL pages, including Apache index) ---
            links_found_on_page = 0
            links_added_to_queue = 0
            potential_links_found = 0

            anchor_tags = soup.find_all("a") # Find all anchor tags

            for link in anchor_tags:
                href_value = link.get("href")
                if not href_value: continue

                href = href_value.strip()
                if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                    continue

                links_found_on_page += 1

                try:
                    absolute_url = urljoin(base_url_for_joining, href)
                    normalized_link_url = normalize_url(absolute_url)
                    if not normalized_link_url: continue

                except ValueError as e:
                    logging.warning(f"Could not join/normalize URL. Base='{base_url_for_joining}', Href='{href}'. Error: {e}")
                    continue
                except Exception as e:
                    logging.error(f"Error processing link. Base='{base_url_for_joining}', Href='{href}'. Error: {e}")
                    continue

                # Check if this NORMALIZED link should be visited
                if self.can_visit(normalized_link_url):
                    potential_links_found += 1
                    if normalized_link_url not in self.visited_urls and normalized_link_url not in self.urls_to_visit:
                        self.urls_to_visit.append(normalized_link_url)
                        links_added_to_queue += 1
                        logging.debug(f"Queueing: {normalized_link_url}")

            logging.debug(f"Links summary for {current_normalized_url}: Found={links_found_on_page}, Potential={potential_links_found}, Added={links_added_to_queue}")
            # --- End Link Processing ---

        except Exception as e:
            logging.error(f"Failed to parse or process page {current_normalized_url}: {e}", exc_info=True)




# --- Main Execution ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Crawl specified domains/paths using Playwright and save pages as Markdown into a domain-specific subdirectory."
    )
    parser.add_argument("--url", required=True, help="The starting URL to crawl (e.g., https://example.com/docs).")
    parser.add_argument("--max-pages", required=True, type=int, help="Maximum number of pages to fetch and save.")
    parser.add_argument("--base-dir", required=True, help="Base directory to save the Markdown files. A subdirectory named after the crawled domain will be created here.")
    parser.add_argument("--extra-domain", default=None, help="An additional domain to allow crawling on (e.g., 'sub.example.com'). Default: None")
    parser.add_argument("--content-selector", default=None, help="Optional CSS selector for the main content area (e.g., 'main', 'article', '.entry-content'). Improves Markdown quality and title extraction.")
    parser.add_argument("--include-metadata", action=argparse.BooleanOptionalAction, default=True, help="Include metadata (like source URL, title) at the top of the Markdown.")
    parser.add_argument("--user-agent", default=None, help="Custom User-Agent string (Playwright uses a default otherwise).")
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True, help="Run the browser in headless mode (no visible window).")
    parser.add_argument("--log-level", default="WARN", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], help="Set the logging level.")

    args = parser.parse_args()

    # --- Set Logging Level from Argument ---
    log_level_numeric = getattr(logging, args.log_level.upper(), None)
    if not isinstance(log_level_numeric, int):
        raise ValueError(f'Invalid log level: {args.log_level}')
    logging.getLogger().setLevel(log_level_numeric)
    logging.info(f"Logging level set to: {args.log_level}")
    # --- End Logging Level Setup ---


    # --- Parse Extra Domain ---
    extra_domain_to_pass = None
    if args.extra_domain:
        parsed_extra = urlparse(args.extra_domain if '//' in args.extra_domain else f"http://{args.extra_domain}")
        if parsed_extra.netloc:
            extra_domain_to_pass = parsed_extra.netloc
            logging.info(f"Parsed --extra-domain as: '{extra_domain_to_pass}'")
        else:
            extra_domain_to_pass = args.extra_domain
            logging.warning(f"Could not parse --extra-domain, using directly: '{extra_domain_to_pass}'")
    # --- End Parse Extra Domain ---

    try:
        crawler = PlaywrightCrawler(
            start_url=args.url,
            max_pages=args.max_pages,
            base_dir=args.base_dir, # Pass base_dir
            include_metadata=args.include_metadata,
            user_agent=args.user_agent,
            content_selector=args.content_selector,
            headless=args.headless,
            extra_domain=extra_domain_to_pass
        )
        crawler.crawl()
    except ValueError as e:
        logging.error(f"Initialization error: {e}")
    except AttributeError as e:
        logging.error(f"Attribute Error: {e}. This might indicate an issue with the script structure or an object.", exc_info=True)
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}", exc_info=True)

