import requests
from bs4 import BeautifulSoup
import logging
from dataclasses import dataclass
from typing import Optional, Dict, List
import json
from plyer import notification
from tenacity import retry, stop_after_attempt, wait_exponential
import time
from datetime import datetime
from colorama import Fore, Style, init
from urllib3 import Retry
import ctypes

# Initialize colorama for Windows
init()


@dataclass
class ProductConfig:
    url: str
    threshold: float
    name: str = ""
    last_price: Optional[float] = None
    last_check: Optional[datetime] = None


class PriceTracker:
    VERSION = "1.0"

    HEADERS = {
        'amazon': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
        },
        'hepsiburada': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
        },
        'trendyol': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
        }
    }

    SELECTORS = {
        'amazon': {
            'price': [
                'span.a-price-whole',
                'span.a-offscreen',
                '#priceblock_ourprice',
                '.a-price .a-offscreen'
            ],
            'title': '#productTitle'
        },
        'hepsiburada': {
            'price': [
                'span[data-test-id="price-current-price"]',
                '[data-test-id="product-price"]'
            ],
            'title': 'h1[data-test-id="product-name"]'
        },
        'trendyol': {
            'price': [
                'span.prc-dsc',
                'span.product-price',
                'div.pr-bx-w span'
            ],
            'title': 'h1.pr-new-br'
        }
    }

    TIMEOUTS = {
        'amazon': (10, 30),
        'hepsiburada': (15, 45),
        'trendyol': (10, 30)
    }

    def __init__(self, config_path: str = "config.json"):
        self.setup_logging()
        self.config = self.load_config(config_path)
        self.session = self.setup_session()
        self.show_banner()

    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('price_tracker.log', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )

    def setup_session(self) -> requests.Session:
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        adapter = requests.adapters.HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=10
        )
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session

    def get_site_type(self, url: str) -> str:
        for site in ['amazon', 'hepsiburada', 'trendyol']:
            if site in url:
                return site
        return 'amazon'  # default fallback

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def extract_price(self, soup: BeautifulSoup, site_type: str) -> Optional[float]:
        try:
            for selector in self.SELECTORS[site_type]['price']:
                price_element = soup.select_one(selector)
                if price_element:
                    price_text = price_element.get_text().strip()
                    price_text = price_text.replace(
                        'TL', '').replace('₺', '').replace(' ', '')
                    price_text = price_text.replace('.', '').replace(',', '.')
                    try:
                        return float(price_text)
                    except ValueError:
                        continue
            return None
        except Exception as e:
            logging.error(f"Price extraction failed: {str(e)}")
            return None

    # Update the send_notification method in main.py

    def send_notification(self, product: ProductConfig, price: float):
        try:
            short_name = f"{product.name[:30]}..." if len(
                product.name) > 30 else product.name
            message = (
                f"Price: ₺{price:.2f}\n"
                f"Threshold: ₺{product.threshold:.2f}"
            )

            # Windows notification using ctypes
            MessageBox = ctypes.windll.user32.MessageBoxW
            MB_ICONINFORMATION = 0x60

            # Show Windows message box (non-blocking)
            ctypes.windll.user32.MessageBoxW(
                0,
                message,
                f"PRICE DROP ALERT! - {short_name}",
                MB_ICONINFORMATION
            )

            # Console notification with colors and box
            print(f"""
    {Fore.GREEN}╔════════════════════════════════════════════╗
    ║             PRICE DROP ALERT!              ║
    ║                                           ║
    ║  Product: {short_name}
    ║  Price: ₺{price:.2f}
    ║  Threshold: ₺{product.threshold:.2f}
    ║  URL: {product.url}                        ║
    ╚════════════════════════════════════════════╝{Style.RESET_ALL}
            """)

            # System beep
            ctypes.windll.kernel32.Beep(1000, 500)

            logging.info(f"Notification sent for {short_name}")

        except Exception as e:
            logging.error(f"Notification failed: {str(e)}")

    def track_product(self, product: ProductConfig) -> Optional[float]:
        site_type = self.get_site_type(product.url)
        timeout = self.TIMEOUTS[site_type]

        try:
            response = self.session.get(
                product.url,
                headers=self.HEADERS[site_type],
                timeout=timeout,
                verify=True,
                allow_redirects=True
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')
            title_selector = self.SELECTORS[site_type]['title']
            title = soup.select_one(title_selector)

            if title:
                product.name = title.get_text().strip()

            price = self.extract_price(soup, site_type)
            if price:
                product.last_check = datetime.now()
                self.print_price_info(product, price)
                if price < product.threshold:
                    self.send_notification(product, price)
                product.last_price = price
                return price

        except Exception as e:
            logging.error(f"Error tracking {product.url}: {str(e)}")
        return None

    def print_price_info(self, product: ProductConfig, current_price: float):
        now = datetime.now().strftime("%H:%M:%S")
        price_color = Fore.GREEN if current_price < product.threshold else Fore.RED

        price_change = ""
        if product.last_price:
            diff = current_price - product.last_price
            if diff > 0:
                price_change = f"{Fore.RED}(↑ +{diff:.2f}){Style.RESET_ALL}"
            elif diff < 0:
                price_change = f"{Fore.GREEN}(↓ {diff:.2f}){Style.RESET_ALL}"

        print(f"""
{Fore.YELLOW}[{now}] Checking: {product.name[:50]}...{Style.RESET_ALL}
Current Price: {price_color}₺{current_price:.2f}{Style.RESET_ALL} {price_change}
Threshold: ₺{product.threshold:.2f}
{'='*50}""")

    def show_banner(self):
        products_count = len(self.config.get('products', []))
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        width = 56  # Fixed width for consistent display

        ascii_art = f"""{Fore.CYAN}
    ╭{'─' * width}╮
    │{' ' * (width+0)}│
    │{' '*4}█▀█ █▀█ █ █▀▀ █▀▀   ▀█▀ █▀█ ▄▀█ █▀▀ █▄▀ █▀▀ █▀█{' '*4}│
    │{' '*4}█▀▀ █▀▄ █ █▄▄ ██▄    █  █▀▄ █▀█ █▄▄ █ █ ██▄ █▀▄{' '*4}│
    │{' ' * (width+0)}│
    │{' '*2}• Active Products: {f"{products_count} item{'s' if products_count != 1 else ''}":<20}{' '*10}│
    │{' '*2}• Start Time: {current_time:<32}{' '*2}│
    │{' '*2}• Author: {Fore.GREEN}Mehmet Kahya{Fore.CYAN:<32}{' '*2}│
    │{' '*2}• Version: {Fore.YELLOW}1.0{Fore.CYAN:<35}{' '*2}│
    │{' ' * (width+0)}│
    ╰{'─' * width}╯{Style.RESET_ALL}"""

        print(ascii_art)
    
    def load_config(self, config_path: str) -> Dict:
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                if not isinstance(config.get('products'), list):
                    raise ValueError("Config must contain 'products' list")
                return config
        except FileNotFoundError:
            logging.warning(
                f"Config file {config_path} not found, using empty config")
            return {"products": []}
        except json.JSONDecodeError:
            logging.error(f"Invalid JSON in {config_path}, using empty config")
            return {"products": []}


def main():
    tracker = PriceTracker()
    check_count = 0

    while True:
        try:
            check_count += 1
            print(f"\n{Fore.CYAN}Check #{
                  check_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Style.RESET_ALL}")

            for product in tracker.config.get('products', []):
                prod_config = ProductConfig(**product)
                tracker.track_product(prod_config)
                time.sleep(1)

            print(f"\n{Fore.YELLOW}Waiting 5 minutes before next check...{
                  Style.RESET_ALL}")
            time.sleep(300)

        except KeyboardInterrupt:
            print(f"\n{Fore.CYAN}Stopping price tracker...{Style.RESET_ALL}")
            break
        except Exception as e:
            logging.error(f"{Fore.RED}Main loop error: {
                          str(e)}{Style.RESET_ALL}")
            time.sleep(60)


if __name__ == "__main__":
    main()
