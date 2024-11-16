# main.py
import tkinter as tk
from tkinter import ttk, messagebox
import requests
from bs4 import BeautifulSoup
import logging
from dataclasses import dataclass
from typing import Optional, Dict, List
import json
import time
from datetime import datetime
from colorama import Fore, Style, init
from urllib3 import Retry
import ctypes
import argparse
import sqlite3
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# Initialize colorama
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
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
        },
        'trendyol': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
        }
    }

    SELECTORS = {
        'amazon': {
            'price': ['span.a-price-whole', 'span.a-offscreen'],
            'title': '#productTitle'
        },
        'hepsiburada': {
            'price': ['span[data-test-id="price-current-price"]'],
            'title': 'h1[data-test-id="product-name"]'
        },
        'trendyol': {
            'price': ['span.prc-dsc', 'span.product-price'],
            'title': 'h1.pr-new-br'
        }
    }

    def __init__(self, config_path: str = "config.json"):
        self.setup_logging()
        self.config = self.load_config(config_path)
        self.setup_database()
        self.session = self.setup_session()

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
        adapter = requests.adapters.HTTPAdapter(max_retries=retry_strategy)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session

    def setup_database(self):
        with sqlite3.connect('price_history.db') as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS price_history (
                    url TEXT,
                    price REAL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def load_config(self, config_path: str) -> Dict:
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                if not isinstance(config.get('products'), list):
                    raise ValueError("Config must contain 'products' list")
                return config
        except FileNotFoundError:
            return {"products": []}

    def get_site_type(self, url: str) -> str:
        if 'amazon' in url:
            return 'amazon'
        elif 'hepsiburada' in url:
            return 'hepsiburada'
        elif 'trendyol' in url:
            return 'trendyol'
        return 'amazon'

    def extract_price(self, soup: BeautifulSoup, site_type: str) -> Optional[float]:
        try:
            for selector in self.SELECTORS[site_type]['price']:
                price_element = soup.select_one(selector)
                if price_element:
                    price_text = price_element.get_text().strip()
                    price_text = price_text.replace(
                        'TL', '').replace('₺', '').replace(' ', '')
                    price_text = price_text.replace('.', '').replace(',', '.')
                    return float(price_text)
            return None
        except Exception as e:
            logging.error(f"Price extraction failed: {str(e)}")
            return None

    def save_price(self, url: str, price: float):
        with sqlite3.connect('price_history.db') as conn:
            conn.execute(
                "INSERT INTO price_history (url, price) VALUES (?, ?)",
                (url, price)
            )

    def get_price_history(self, url: str) -> List[tuple]:
        with sqlite3.connect('price_history.db') as conn:
            cursor = conn.execute(
                "SELECT timestamp, price FROM price_history WHERE url = ? ORDER BY timestamp",
                (url,)
            )
            return cursor.fetchall()

    def plot_price_history(self, url: str, ax):
        history = self.get_price_history(url)
        if not history:
            return

        dates = [datetime.strptime(h[0], '%Y-%m-%d %H:%M:%S') for h in history]
        prices = [h[1] for h in history]

        ax.plot(dates, prices)
        ax.set_title('Price History')
        ax.set_xlabel('Date')
        ax.set_ylabel('Price (TRY)')
        plt.xticks(rotation=45)
        plt.tight_layout()

    def send_notification(self, product: ProductConfig, price: float):
        try:
            short_name = f"{product.name[:30]}..." if len(
                product.name) > 30 else product.name
            message = f"""
💰 Current Price: ₺{price:.2f}
🎯 Target Price: ₺{product.threshold:.2f}
📊 Savings: ₺{product.threshold - price:.2f}

{product.url}
"""
            MessageBox = ctypes.windll.user32.MessageBoxW
            MB_ICONINFORMATION = 0x40

            ctypes.windll.user32.MessageBoxW(
                0, message, f"Price Drop! - {short_name}", MB_ICONINFORMATION)
            ctypes.windll.kernel32.Beep(1000, 500)  # Beep sound

            logging.info(f"Notification sent for {short_name}")
        except Exception as e:
            logging.error(f"Notification failed: {str(e)}")

    def track_product(self, product: ProductConfig) -> Optional[float]:
        site_type = self.get_site_type(product.url)
        try:
            response = self.session.get(
                product.url,
                headers=self.HEADERS[site_type],
                timeout=30
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            title = soup.select_one(self.SELECTORS[site_type]['title'])
            if title:
                product.name = title.get_text().strip()

            price = self.extract_price(soup, site_type)
            if price:
                self.save_price(product.url, price)
                if price < product.threshold:
                    self.send_notification(product, price)
                return price

        except Exception as e:
            logging.error(f"Error tracking {product.url}: {str(e)}")
        return None


class PriceTrackerGUI(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Price Tracker v1.0")
        self.geometry("800x600")

        self.tracker = PriceTracker()

        self.main_frame = ttk.Frame(self)
        self.main_frame.pack(expand=True, fill='both', padx=10, pady=10)

        self.create_table()
        self.create_controls()
        self.after(1000, self.update_prices)

    def create_table(self):
        columns = ('Product', 'Current Price', 'Target', 'Site', 'Status')
        self.tree = ttk.Treeview(
            self.main_frame, columns=columns, show='headings')

        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=150)

        self.tree.pack(expand=True, fill='both')

        scrollbar = ttk.Scrollbar(
            self.main_frame, orient='vertical', command=self.tree.yview)
        scrollbar.pack(side='right', fill='y')
        self.tree.configure(yscrollcommand=scrollbar.set)

    def create_controls(self):
        control_frame = ttk.Frame(self.main_frame)
        control_frame.pack(fill='x', pady=10)

        ttk.Button(control_frame, text="Add Product",
                   command=self.add_product).pack(side='left', padx=5)
        ttk.Button(control_frame, text="Remove Product",
                   command=self.remove_product).pack(side='left', padx=5)
        ttk.Button(control_frame, text="Show History",
                   command=self.show_history).pack(side='left', padx=5)
        ttk.Button(control_frame, text="Quit", command=self.quit).pack(
            side='right', padx=5)
        

    def update_prices(self):
        self.tree.delete(*self.tree.get_children())

        for product in self.tracker.config.get('products', []):
            prod_config = ProductConfig(**product)
            price = self.tracker.track_product(prod_config)

            if price:
                status = "✅" if price < prod_config.threshold else "❌"
                self.tree.insert('', 'end', values=(
                    prod_config.name,
                    f"₺{price:.2f}",
                    f"₺{prod_config.threshold:.2f}",
                    self.tracker.get_site_type(prod_config.url),
                    status,
                    prod_config.url  # Include URL as hidden value
                ))
        # 1 minutes (before 300000 => 5 minutes)
        self.after(300000, self.update_prices)

    def add_product(self):
        dialog = AddProductDialog(self)
        self.wait_window(dialog)

    def remove_product(self):
        selected = self.tree.selection()
        if selected:
            self.tree.delete(selected)

    def show_history(self):
        selected = self.tree.selection()
        if selected:
            item = self.tree.item(selected[0])
            url = item['values'][5]  # Index 5 corresponds to the URL
            HistoryDialog(self, url, self.tracker)
            
    def quit(self):
        return super().quit()

    def create_table(self):
        columns = ('Product', 'Current Price',
                   'Target', 'Site', 'Status', 'URL')
        self.tree = ttk.Treeview(
            self.main_frame, columns=columns, show='headings')

        # Only show the first five columns
        self.tree['displaycolumns'] = (
            'Product', 'Current Price', 'Target', 'Site', 'Status')

        for col in ('Product', 'Current Price', 'Target', 'Site', 'Status'):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=150)

        self.tree.pack(expand=True, fill='both')

        scrollbar = ttk.Scrollbar(
            self.main_frame, orient='vertical', command=self.tree.yview)
        scrollbar.pack(side='right', fill='y')
        self.tree.configure(yscrollcommand=scrollbar.set)


class AddProductDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Add Product")

        ttk.Label(self, text="URL:").grid(row=0, column=0, padx=5, pady=5)
        self.url = ttk.Entry(self, width=50)
        self.url.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(self, text="Threshold:").grid(
            row=1, column=0, padx=5, pady=5)
        self.threshold = ttk.Entry(self)
        self.threshold.grid(row=1, column=1, padx=5, pady=5)

        ttk.Button(self, text="Add", command=self.add).grid(
            row=2, column=0, columnspan=2, pady=10)

    def add(self):
        try:
            url = self.url.get()
            threshold = float(self.threshold.get())

            with open('config.json', 'r+', encoding='utf-8') as f:
                config = json.load(f)
                config['products'].append({
                    'url': url,
                    'threshold': threshold
                })
                f.seek(0)
                json.dump(config, f, indent=4)
                f.truncate()

            self.destroy()
        except ValueError:
            messagebox.showerror("Error", "Invalid threshold value")
        except Exception as e:
            messagebox.showerror("Error", str(e))


class HistoryDialog(tk.Toplevel):
    def __init__(self, parent, url, tracker):
        super().__init__(parent)
        self.title("Price History")
        self.geometry("800x600")

        # Create figure with larger size
        fig, ax = plt.subplots(figsize=(10, 6))

        # Get price history data
        history = tracker.get_price_history(url)
        if history:
            dates = [datetime.strptime(h[0], '%Y-%m-%d %H:%M:%S')
                     for h in history]
            prices = [h[1] for h in history]

            # Plot with markers and line
            ax.plot(dates, prices, 'bo-', markersize=6,
                    linewidth=2, label='Price')

            # Add grid
            ax.grid(True, linestyle='--', alpha=0.7)

            # Format y-axis as currency
            ax.yaxis.set_major_formatter(
                plt.FuncFormatter(lambda x, p: f'₺{x:,.2f}'))

            # Rotate x-axis dates
            plt.xticks(rotation=45, ha='right')

            # Add labels and title
            ax.set_title('Price History', pad=20,
                         fontsize=12, fontweight='bold')
            ax.set_xlabel('Date', labelpad=10)
            ax.set_ylabel('Price (TRY)', labelpad=10)

            # Add legend
            ax.legend()

            # Show min/max prices
            min_price = min(prices)
            max_price = max(prices)
            ax.axhline(y=min_price, color='g', linestyle='--', alpha=0.5)
            ax.axhline(y=max_price, color='r', linestyle='--', alpha=0.5)

            # Add price annotations
            for i, (date, price) in enumerate(zip(dates, prices)):
                ax.annotate(f'₺{price:,.2f}',
                            (date, price),
                            xytext=(5, 5),
                            textcoords='offset points',
                            fontsize=8)
        else:
            ax.text(0.5, 0.5, 'No price history available',
                    horizontalalignment='center',
                    verticalalignment='center',
                    transform=ax.transAxes)

        # Adjust layout
        plt.tight_layout()

        # Create canvas
        canvas = FigureCanvasTkAgg(fig, master=self)
        canvas.draw()
        canvas.get_tk_widget().pack(expand=True, fill='both', padx=10, pady=10)


def main():
    app = PriceTrackerGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
