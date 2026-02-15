#!/usr/bin/env python3
"""
HMS Archive RSS Feed Generator
Auto-updates via GitHub Actions
"""

import requests
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime
import html
import re

def clean_html_for_rss(html_content):
    """
    Clean HTML content while preserving important formatting.
    Removes excessive nested spans and inline styles, keeps semantic tags.
    """
    if not html_content:
        return ""
    
    # First, unescape any HTML entities
    content = html.unescape(html_content)
    
    # Remove dir="ltr" and dir="rtl" attributes
    content = re.sub(r'\s+dir="[^"]*"', '', content)
    
    # Remove style attributes (inline CSS)
    content = re.sub(r'\s+style="[^"]*"', '', content)
    
    # Remove excessive nested spans - replace <span><span>...</span></span> with just the content
    # This handles the common pattern of multiple nested spans
    while re.search(r'<span[^>]*>\s*<span', content):
        content = re.sub(r'<span[^>]*>(\s*<span)', r'\1', content)
        content = re.sub(r'</span>(\s*</span>)', r'\1', content)
    
    # Remove remaining empty spans
    content = re.sub(r'<span[^>]*>\s*</span>', '', content)
    
    # Remove spans that only wrap text (convert <span>text</span> to just text)
    # But keep spans that contain other tags
    content = re.sub(r'<span[^>]*>([^<]+)</span>', r'\1', content)
    
    # Clean up multiple consecutive spaces
    content = re.sub(r'\s+', ' ', content)
    
    # Clean up spaces around tags
    content = re.sub(r'>\s+<', '><', content)
    
    # Ensure proper paragraph spacing
    content = re.sub(r'</p>\s*<p', '</p>\n<p', content)
    
    # Convert <b> to <strong> and <i> to <em> for semantic HTML
    content = re.sub(r'<b(\s|>)', r'<strong\1', content)
    content = re.sub(r'</b>', r'</strong>', content)
    content = re.sub(r'<i(\s|>)', r'<em\1', content)
    content = re.sub(r'</i>', r'</em>', content)
    
    return content.strip()

def clean_html_to_text(text):
    """Remove ALL HTML tags from text for description field"""
    if not text:
        return ""
    clean = re.sub('<.*?>', '', text)
    clean = html.unescape(clean)
    # Clean up multiple spaces and newlines
    clean = re.sub(r'\s+', ' ', clean)
    return clean.strip()

def fetch_all_stories(results_per_page=50):
    """Fetch all stories from the HMS archive API"""
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
    """Generate RSS 2.0 XML feed from stories"""
    
    rss = ET.Element('rss', version='2.0')
    rss.set('xmlns:atom', 'http://www.w3.org/2005/Atom')
    rss.set('xmlns:content', 'http://purl.org/rss/1.0/modules/content/')
    
    channel = ET.SubElement(rss, 'channel')
    
    ET.SubElement(channel, 'title').text = "JEM.tv - Here's My Story Archive"
    ET.SubElement(channel, 'link').text = "https://videos.jem.tv/hms/archive"
    ET.SubElement(channel, 'description').text = "Stories from the Here's My Story archive at JEM.tv - Auto-updated daily"
    ET.SubElement(channel, 'language').text = "en-us"
    ET.SubElement(channel, 'lastBuildDate').text = datetime.now().strftime('%a, %d %b %Y %H:%M:%S GMT')
    
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
        
        # Description: plain text only (for RSS readers that don't support HTML)
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
