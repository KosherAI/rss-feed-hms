#!/usr/bin/env python3
"""
HMS Archive RSS Feed Generator
Auto-updates via GitHub Actions
"""

import requests
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime
from bs4 import BeautifulSoup
import html
import re


# Tags to keep in the cleaned HTML (semantic/formatting tags)
ALLOWED_TAGS = {
    'p', 'br', 'strong', 'b', 'em', 'i', 'u',
    'a', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'ul', 'ol', 'li', 'blockquote', 'hr', 'sub', 'sup',
}

# Attributes to keep (only href on links)
ALLOWED_ATTRS = {
    'a': ['href'],
}


def clean_html_for_rss(html_content):
    """
    Clean HTML content using BeautifulSoup for robust parsing.
    Strips all inline styles, classes, and junk tags (span, div wrappers)
    while preserving meaningful formatting (p, strong, em, a, h1-h6, lists, etc).
    """
    if not html_content:
        return ""

    soup = BeautifulSoup(html_content, "html.parser")

    # Convert <b> to <strong> and <i> to <em> for semantic HTML
    for tag in soup.find_all('b'):
        tag.name = 'strong'
    for tag in soup.find_all('i'):
        tag.name = 'em'

    # Unwrap all tags that are not in ALLOWED_TAGS (e.g., span, div, font)
    # unwrap() replaces the tag with its children, preserving inner content
    for tag in soup.find_all(True):
        if tag.name not in ALLOWED_TAGS:
            tag.unwrap()

    # Strip all attributes except allowed ones
    for tag in soup.find_all(True):
        allowed = ALLOWED_ATTRS.get(tag.name, [])
        attrs_to_remove = [attr for attr in tag.attrs if attr not in allowed]
        for attr in attrs_to_remove:
            del tag[attr]

    # Remove empty/whitespace-only tags (except <br> and <hr>)
    # If a tag contains only whitespace or non-breaking spaces, replace
    # it with a plain space to avoid merging adjacent words.
    # Example: 'audience<em>\xa0</em>before' -> 'audience before'
    for tag in soup.find_all(True):
        if tag.name not in ('br', 'hr') and not tag.find_all(True):
            inner_text = tag.get_text()
            # Check if the tag has only whitespace/nbsp (no real content)
            has_only_whitespace = not inner_text.replace('\u00a0', '').strip()
            if has_only_whitespace:
                if inner_text:
                    # Had whitespace/nbsp content - replace with a space
                    tag.replace_with(' ')
                else:
                    # Truly empty tag - remove it
                    tag.decompose()

    # Get the cleaned HTML string
    cleaned = str(soup)

    # Normalize non-breaking spaces to regular spaces
    cleaned = cleaned.replace('\u00a0', ' ')

    # Clean up multiple spaces (but not inside tags)
    cleaned = re.sub(r' {2,}', ' ', cleaned)

    # Clean up whitespace between tags
    cleaned = re.sub(r'\n\s*\n', '\n', cleaned)
    cleaned = cleaned.strip()

    return cleaned


def clean_html_to_text(text):
    """Remove ALL HTML tags from text for the description field."""
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    clean = soup.get_text(separator=' ')
    clean = re.sub(r'\s+', ' ', clean)
    return clean.strip()


def fetch_all_stories(results_per_page=50):
    """Fetch all stories from the HMS archive API."""
    base_url = "https://5qlaecnhel.execute-api.us-east-1.amazonaws.com/prod/ashreinu/api/v1/unlocked/heres-my-story-archive"
    all_stories = []
    page = 1

    while True:
        params = {
            'page': page,
            'results_per_page': results_per_page,
            'language': 'en'
        }

        print(f"Fetching page {page}...")
        try:
            response = requests.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            stories = data.get('data', [])
            if not stories:
                break

            all_stories.extend(stories)

            meta = data.get('meta', {})
            if page >= meta.get('total_pages', 1):
                break

            page += 1

        except Exception as e:
            print(f"Error fetching page {page}: {e}")
            break

    print(f"Total stories fetched: {len(all_stories)}")
    return all_stories


def create_rss_feed(stories, output_file='feed.xml'):
    """Generate RSS 2.0 XML feed from stories."""

    rss = ET.Element('rss', version='2.0')
    rss.set('xmlns:atom', 'http://www.w3.org/2005/Atom')
    rss.set('xmlns:content', 'http://purl.org/rss/1.0/modules/content/')

    channel = ET.SubElement(rss, 'channel')

    ET.SubElement(channel, 'title').text = "JEM.tv - Here's My Story Archive"
    ET.SubElement(channel, 'link').text = "https://videos.jem.tv/hms/archive"
    ET.SubElement(channel, 'description').text = (
        "Stories from the Here's My Story archive at JEM.tv - Auto-updated hourly"
    )
    ET.SubElement(channel, 'language').text = "en-us"
    ET.SubElement(channel, 'lastBuildDate').text = datetime.utcnow().strftime(
        '%a, %d %b %Y %H:%M:%S GMT'
    )

    for story in stories:
        item = ET.SubElement(channel, 'item')

        title = story.get('name', 'Untitled Story')
        ET.SubElement(item, 'title').text = title

        link = story.get('link', '')
        if link:
            ET.SubElement(item, 'link').text = link
            ET.SubElement(item, 'guid', isPermaLink='true').text = link
        else:
            story_id = story.get('id', '')
            ET.SubElement(item, 'guid', isPermaLink='false').text = str(story_id)

        # Description: plain text only (for readers that don't support HTML)
        description = story.get('description') or story.get('content', '')
        if description:
            clean_desc = clean_html_to_text(description)
            if len(clean_desc) > 300:
                clean_desc = clean_desc[:297] + '...'
            ET.SubElement(item, 'description').text = clean_desc

        # Content: cleaned HTML with proper formatting preserved
        content = story.get('content', '')
        if content:
            cleaned_content = clean_html_for_rss(content)
            content_elem = ET.SubElement(item, 'content:encoded')
            content_elem.text = cleaned_content

        image = story.get('image') or story.get('thumbnail')
        if image:
            enclosure = ET.SubElement(item, 'enclosure')
            enclosure.set('url', image)
            enclosure.set('type', 'image/jpeg')

        issue = story.get('issue_number')
        if issue:
            ET.SubElement(item, 'category').text = f"Issue {issue}"

    xml_string = ET.tostring(rss, encoding='utf-8')
    dom = minidom.parseString(xml_string)
    pretty_xml = dom.toprettyxml(indent='  ', encoding='utf-8')

    with open(output_file, 'wb') as f:
        f.write(pretty_xml)

    print(f"RSS feed generated: {output_file}")
    print(f"Total items in feed: {len(stories)}")


if __name__ == "__main__":
    stories = fetch_all_stories()
    create_rss_feed(stories)
