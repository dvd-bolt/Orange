import os
import logging
from typing import List, Dict, Any, Tuple
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("web_aut")

class MockPage:
    async def goto(self, url):
        pass
    async def content(self):
        return "<html><body><button id='btn'>Mock Page</button></body></html>"
    async def screenshot(self, path=None):
        if path:
            img = Image.new('RGB', (800, 600), color=(255, 255, 255))
            img.save(path)
        return b""

class CDPConnector:
    """
    CDPConnector attaches to active Chrome instances via Playwright CDP.
    """
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    async def attach_cdp(self, endpoint: str = "http://localhost:9222") -> Any:
        """
        Connects over CDP to the specified endpoint.
        If it fails, it launches a fallback headless browser instance for testing.
        """
        from playwright.async_api import async_playwright
        self.playwright = await async_playwright().start()
        try:
            logger.info(f"Connecting to CDP endpoint: {endpoint}")
            self.browser = await self.playwright.chromium.connect_over_cdp(endpoint)
            self.context = self.browser.contexts[0]
            self.page = self.context.pages[0]
            logger.info("Successfully connected to active CDP session.")
        except Exception as e:
            logger.warning(f"Failed to connect to CDP: {e}. Launching fallback headless browser.")
            try:
                self.browser = await self.playwright.chromium.launch(headless=True)
                self.context = await self.browser.new_context()
                self.page = await self.context.new_page()
            except Exception as e2:
                logger.warning(f"Failed to launch browser: {e2}. Returning MockPage.")
                self.page = MockPage()
        return self.page

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()


class DOMParser:
    """
    DOMParser extracts and lists interactive elements from the DOM.
    """
    @staticmethod
    def parse_interactive_elements(html: str) -> List[Dict[str, Any]]:
        """
        Parses HTML to find interactive elements (buttons, links, inputs, etc.)
        and assigns them sequential IDs.
        """
        soup = BeautifulSoup(html, 'html.parser')
        interactive_tags = ['a', 'button', 'input', 'select', 'textarea']
        elements = []
        element_id = 1

        for tag in soup.find_all(interactive_tags):
            # Exclude hidden or non-visible elements
            if tag.get('type') == 'hidden':
                continue
                
            text = tag.get_text(strip=True) or tag.get('placeholder') or tag.get('aria-label') or tag.get('value') or ""
            element_type = tag.name
            if tag.name == 'input':
                element_type = f"input[{tag.get('type', 'text')}]"
                
            # Estimate a mock bounding box if we are parsing raw HTML without a real viewport
            # Format: [x, y, width, height]
            bbox = [10 + (element_id * 5) % 100, 50 + (element_id * 30), 100, 25]
            
            elements.append({
                "id": element_id,
                "tag": tag.name,
                "type": element_type,
                "text": text,
                "selector": DOMParser._get_selector(tag),
                "bbox": bbox
            })
            element_id += 1

        return elements

    @staticmethod
    def _get_selector(element) -> str:
        """Generates a simple CSS selector for an element."""
        if element.get('id'):
            return f"#{element['id']}"
        classes = element.get('class')
        class_str = f".{'.'.join(classes)}" if classes else ""
        return f"{element.name}{class_str}"


class VisionAnnotator:
    """
    VisionAnnotator draws visual markup (rectangles and labels) on a page screenshot.
    """
    @staticmethod
    def annotate_screenshot(screenshot_path: str, elements: List[Dict[str, Any]], output_path: str) -> str:
        """
        Draws bounding box outlines and ID label tags onto the screenshot image.
        """
        if not os.path.exists(screenshot_path):
            # Create a blank temporary image if it doesn't exist
            img = Image.new('RGB', (800, 600), color=(255, 255, 255))
            img.save(screenshot_path)
            
        with Image.open(screenshot_path) as img:
            draw = ImageDraw.Draw(img)
            
            # Try loading default font or fallback
            try:
                font = ImageFont.load_default()
            except Exception:
                font = None

            for el in elements:
                bbox = el.get("bbox", [0, 0, 0, 0])
                el_id = el.get("id", 0)
                
                x, y, w, h = bbox
                # Draw outer bounding box
                draw.rectangle([x, y, x + w, y + h], outline="red", width=2)
                
                # Draw numbered label badge
                label = str(el_id)
                draw.rectangle([x, y - 12, x + 18, y], fill="red")
                if font:
                    draw.text((x + 4, y - 11), label, fill="white", font=font)
                else:
                    draw.text((x + 4, y - 11), label, fill="white")
                    
            img.save(output_path)
        return output_path
