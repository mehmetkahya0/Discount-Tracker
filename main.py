# main.py

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import requests
from bs4 import BeautifulSoup
import logging
from dataclasses import dataclass
from typing import Optional, Dict, List
import json
from datetime import datetime
import ctypes
import sqlite3
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import webbrowser
import csv
import psutil
from memory_profiler import memory_usage

# For Windows High DPI scaling
if hasattr(ctypes, 'windll'):
    ctypes.windll.shcore.SetProcessDpiAwareness(1)

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
            'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
                           ' AppleWebKit/537.36 (KHTML, like Gecko)'
                           ' Chrome/94.0.4606.61 Safari/537.36'),
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
        },
        'hepsiburada': {
            'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
                           ' Chrome/120.0.0.0'),
            'Accept': 'text/html,application/xhtml+xml,application/xml;'
                      'q=0.9,*/*;q=0.8',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
        },
        'trendyol': {
            'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
                           ' Chrome/120.0.0.0'),
            'Accept': 'text/html,application/xhtml+xml,application/xml;'
                      'q=0.9,*/*;q=0.8',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
        }
    }

    SELECTORS = {
        'amazon': {
            'price': [
                'span#priceblock_ourprice', 'span#priceblock_dealprice',
                'span.a-price-whole', 'span.a-offscreen'
            ],
            'title': '#productTitle'
        },
        'hepsiburada': {
            'price': [
                'span[data-bind="markupText: currentPriceBeforePoint"]',
                'span[data-bind="markupText: currentPriceAfterPoint"]',
                'span#offering-price'
            ],
            'title': 'h1.product-name'
        },
        'trendyol': {
            'price': ['span.prc-dsc', 'span.prc-org', 'span.product-price'],
            'title': 'h1.pr-new-br'
        }
    }

    def setup_session(self) -> requests.Session:
        session = requests.Session()
        retry_strategy = requests.adapters.Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD"]
        )
        adapter = requests.adapters.HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

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
            logging.warning(f"Config file {config_path} not found")
            return {"products": []}

    def get_site_type(self, url: str) -> str:
        if 'amazon' in url:
            return 'amazon'
        elif 'hepsiburada' in url:
            return 'hepsiburada'
        elif 'trendyol' in url:
            return 'trendyol'
        return 'amazon'  # Default to Amazon

    def extract_price(self, soup: BeautifulSoup, site_type: str) -> Optional[float]:
        try:
            for selector in self.SELECTORS[site_type]['price']:
                price_element = soup.select_one(selector)
                if price_element:
                    price_text = price_element.get_text().strip()
                    price_text = price_text.replace('TL', '').replace('₺', '').replace(' ', '')
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

    def track_product(self, product: ProductConfig) -> Optional[float]:
        site_type = self.get_site_type(product.url)
        try:
            response = self.session.get(
                product.url,
                headers=self.HEADERS[site_type],
                timeout=10  # Reduced timeout
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

        except requests.exceptions.RequestException as e:
            logging.error(f"Network error for {product.url}: {str(e)}")
        except Exception as e:
            logging.error(f"Error tracking {product.url}: {str(e)}")
        return None

    def send_notification(self, product: ProductConfig, price: float):
        try:
            short_name = f"{product.name[:30]}..." if len(product.name) > 30 else product.name
            message = f"""
💰 Current Price: ₺{price:.2f}
🎯 Target Price: ₺{product.threshold:.2f}
📊 Savings: ₺{product.threshold - price:.2f}

{product.url}
"""
            MessageBox = ctypes.windll.user32.MessageBoxW
            MB_ICONINFORMATION = 0x40

            ctypes.windll.user32.MessageBoxW(
                0, message, f"Price Drop! - {short_name}", MB_ICONINFORMATION
            )
            ctypes.windll.kernel32.Beep(1000, 500)  # Beep sound

            logging.info(f"Notification sent for {short_name}")
        except Exception as e:
            logging.error(f"Notification failed: {str(e)}")

class PriceTrackerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Price Tracker v1.0")
        self.geometry("1000x700")
        self.tracker = PriceTracker()
        self.products_data = []  # Initialize products data list
        self.main_frame = ttk.Frame(self)
        self.main_frame.pack(expand=True, fill='both', padx=10, pady=10)
        self.create_table()
        self.create_controls()
        self.create_resource_usage_label()
        self.update_resource_usage()
        self.after(0, self.update_prices)  # Immediate update

        # Add ASCII logo to the window
        logo_text = """
█▀█ █▀█ █ █▀▀ █▀▀   ▀█▀ █▀█ ▄▀█ █▀▀ █▄▀ █▀▀ █▀█
█▀▀ █▀▄ █ █▄▄ ██▄    █  █▀▄ █▀█ █▄▄ █ █ ██▄ █▀▄"""
        ttk.Label(self.main_frame, text=logo_text, font=("Courier", 12, "bold")).pack(
            pady=(10, 20))

    def create_resource_usage_label(self):
        self.resource_label = ttk.Label(self.main_frame, text="", font=("Helvetica", 10))
        self.resource_label.pack(pady=(5, 5))

    def update_resource_usage(self):
        # Get current process
        process = psutil.Process()

        # Get RAM usage in MB
        ram_usage = process.memory_info().rss / (1024 * 1024)

        # Get CPU usage percentage
        cpu_usage = process.cpu_percent(interval=1)

        # Update the label text
        self.resource_label.config(
            text=f"CPU Usage: {cpu_usage:.1f}%   RAM Usage: {ram_usage:.1f} MB"
        )

        # Schedule to update every second
        self.after(1000, self.update_resource_usage)

    def create_table(self):
        columns = ('Product', 'Current Price',
                   'Target', 'Site', 'Status', 'URL')
        self.tree = ttk.Treeview(
            self.main_frame, columns=columns, show='headings'
        )

        self.tree['displaycolumns'] = columns[:-1]  # Exclude URL from display

        for col in columns[:-1]:  # Exclude URL
            self.tree.heading(col, text=col)
            self.tree.column(col, width=150)

        self.tree.pack(expand=True, fill='both')

        scrollbar = ttk.Scrollbar(
            self.tree, orient='vertical', command=self.tree.yview
        )
        scrollbar.pack(side='right', fill='y')
        self.tree.configure(yscrollcommand=scrollbar.set)

        # Bind double-click event
        self.tree.bind('<Double-1>', lambda e: self.go_to_product())

    def create_controls(self):
        control_frame = ttk.Frame(self.main_frame)
        control_frame.pack(fill='x', pady=10)

        # Left side buttons
        left_frame = ttk.Frame(control_frame)
        left_frame.pack(side='left')

        ttk.Button(
            left_frame, text="Add Product",
            command=self.add_product
        ).pack(side='left', padx=5)

        ttk.Button(
            left_frame, text="Remove Product",
            command=self.remove_product
        ).pack(side='left', padx=5)

        ttk.Button(
            left_frame, text="Show Price History",
            command=self.show_history
        ).pack(side='left', padx=5)

        ttk.Button(
            left_frame, text="Go to Product",
            command=self.go_to_product
        ).pack(side='left', padx=5)

        ttk.Button(
            left_frame, text="🔄 Refresh",
            command=self.update_prices
        ).pack(side='left', padx=5)

        # Middle frame for search
        middle_frame = ttk.Frame(control_frame)
        middle_frame.pack(side='left', padx=20, fill='x', expand=True)

        self.search_var = tk.StringVar()
        self.search_var.trace('w', self.on_search_change)

        self.search_entry = ttk.Entry(
            middle_frame, textvariable=self.search_var
        )
        self.search_entry.pack(side='left', fill='x', expand=True)

        # Add placeholder behavior
        self.search_entry.insert(0, "Search products...")
        self.search_entry.bind('<FocusIn>', self._on_search_focus_in)
        self.search_entry.bind('<FocusOut>', self._on_search_focus_out)

        # Right side buttons
        right_frame = ttk.Frame(control_frame)
        right_frame.pack(side='right')

        ttk.Button(
            right_frame, text="Export CSV",
            command=self.export_csv
        ).pack(side='right', padx=5)

        ttk.Button(
            right_frame, text="Info",
            command=self.info
        ).pack(side='right', padx=5)

        ttk.Button(
            right_frame, text="Quit",
            command=self.quit
        ).pack(side='right', padx=5)

    def _on_search_focus_in(self, event):
        """Clear placeholder text when entry gains focus"""
        if self.search_entry.get() == "Search products...":
            self.search_entry.delete(0, tk.END)

    def _on_search_focus_out(self, event):
        """Restore placeholder text when entry loses focus"""
        if not self.search_entry.get():
            self.search_entry.insert(0, "Search products...")

    def on_search_change(self, *args):
        search_text = self.search_var.get().lower()

        # Skip if placeholder text or empty
        if search_text == "" or search_text == "search products...":
            self.show_products(self.products_data)
            return

        # Filter products based on search text
        filtered_products = [
            product for product in self.products_data
            if search_text in product['name'].lower()
        ]

        self.show_products(filtered_products)

    def update_prices(self):
        self.products_data = []  # Reset the product data list

        for product in self.tracker.config.get('products', []):
            prod_config = ProductConfig(**product)
            price = self.tracker.track_product(prod_config)

            if price:
                status = "✅" if price < prod_config.threshold else "❌"
                product_entry = {
                    'name': prod_config.name,
                    'price': price,
                    'threshold': prod_config.threshold,
                    'site': self.tracker.get_site_type(prod_config.url),
                    'status': status,
                    'url': prod_config.url
                }
                self.products_data.append(product_entry)

        self.show_products(self.products_data)

        # Schedule the next update
        self.after(300000, self.update_prices)  # Update every 5 minutes

    def show_products(self, products):
        self.tree.delete(*self.tree.get_children())

        for product in products:
            self.tree.insert('', 'end', values=(
                product['name'],
                f"₺{product['price']:.2f}",
                f"₺{product['threshold']:.2f}",
                product['site'],
                product['status'],
                product['url']
            ))

    def add_product(self):
        dialog = AddProductDialog(self)
        self.wait_window(dialog)
        self.update_prices()

    def remove_product(self):
        selected = self.tree.selection()
        if selected:
            if messagebox.askyesno("Confirm", "Remove selected product?"):
                item = self.tree.item(selected[0])
                url = item['values'][5]  # URL is in hidden column

                with open('config.json', 'r+', encoding='utf-8') as f:
                    config = json.load(f)
                    config['products'] = [p for p in config['products'] if p['url'] != url]
                    f.seek(0)
                    json.dump(config, f, indent=4)
                    f.truncate()

                self.tree.delete(selected)

    def show_history(self):
        selected = self.tree.selection()
        if selected:
            item = self.tree.item(selected[0])
            url = item['values'][5]  # URL is in hidden column
            HistoryDialog(self, url, self.tracker)

    def go_to_product(self):
        selected = self.tree.selection()
        if selected:
            item = self.tree.item(selected[0])
            url = item['values'][5]
            self.open_product_url(url)

    def open_product_url(self, url):
        webbrowser.open(url)

    def export_csv(self):
        filename = filedialog.asksaveasfilename(
            defaultextension='.csv',
            filetypes=[('CSV files', '*.csv')]
        )
        if filename:
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Product', 'Current Price', 'Target', 'Site', 'Status'])
                for item in self.tree.get_children():
                    values = self.tree.item(item)['values']
                    writer.writerow(values[:-1])  # Exclude URL
            messagebox.showinfo("Export CSV", f"Data exported to {filename}")

    def info(self):
        about = tk.Toplevel(self)
        about.title("About Price Tracker")
        about.geometry("600x400")
        about.resizable(False, False)

        # Center window
        about.transient(self)
        about.grab_set()

        style = ttk.Style()
        style.configure("Title.TLabel", font=("Helvetica", 12, "bold"))
        style.configure("Info.TLabel", font=("Helvetica", 10))

        main_frame = ttk.Frame(about, padding="20")
        main_frame.pack(fill='both', expand=True)

        # ASCII Logo
        logo_text = """
█▀█ █▀█ █ █▀▀ █▀▀   ▀█▀ █▀█ ▄▀█ █▀▀ █▄▀ █▀▀ █▀█
█▀▀ █▀▄ █ █▄▄ ██▄    █  █▀▄ █▀█ █▄▄ █ █ ██▄ █▀▄"""
        logo = ttk.Label(main_frame, text=logo_text, font=("Courier", 12, "bold"))
        logo.pack(pady=(0, 20))

        # Version info
        ttk.Label(
            main_frame,
            text=f"Version {self.tracker.VERSION}",
            style="Title.TLabel"
        ).pack(pady=(0, 10))

        # Supported sites
        ttk.Label(
            main_frame,
            text="Supported Sites:",
            style="Title.TLabel"
        ).pack(pady=(10, 5))

        sites_frame = ttk.Frame(main_frame)
        sites_frame.pack(pady=(0, 20))

        for site in ["Amazon.com.tr", "Trendyol", "Hepsiburada"]:
            ttk.Label(
                sites_frame,
                text=f"• {site}",
                style="Info.TLabel"
            ).pack()

        # Developer info
        ttk.Label(
            main_frame,
            text="Developed by Mehmet Kahya",
            style="Info.TLabel"
        ).pack(pady=(10, 5))

        # GitHub link
        github_link = ttk.Label(
            main_frame,
            text="github.com/mehmetkahya0",
            style="Info.TLabel",
            cursor="hand2",
            foreground="blue"
        )
        github_link.pack()
        github_link.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/mehmetkahya0"))

        # Close button
        ttk.Button(
            main_frame,
            text="Close",
            command=about.destroy
        ).pack(pady=(20, 0))

class AddProductDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Add Product")

        ttk.Label(self, text="URL:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
        self.url = ttk.Entry(self, width=50)
        self.url.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(self, text="Threshold (₺):").grid(row=1, column=0, padx=5, pady=5, sticky='e')
        self.threshold = ttk.Entry(self)
        self.threshold.grid(row=1, column=1, padx=5, pady=5)

        ttk.Button(self, text="Add", command=self.add).grid(
            row=2, column=0, columnspan=2, pady=10)

        self.url.focus_set()

    def add(self):
        try:
            url = self.url.get().strip()
            threshold = float(self.threshold.get().replace(',', '.'))

            if not url:
                messagebox.showerror("Error", "URL cannot be empty")
                return

            if not threshold or threshold <= 0:
                messagebox.showerror("Error", "Threshold must be a positive number")
                return

            with open('config.json', 'r+', encoding='utf-8') as f:
                config = json.load(f)
                # Check if product already exists
                if any(p['url'] == url for p in config['products']):
                    messagebox.showwarning("Warning", "Product already exists")
                    return

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

        fig, ax = plt.subplots(figsize=(10, 6))
        canvas = FigureCanvasTkAgg(fig, master=self)
        canvas.draw()
        canvas.get_tk_widget().pack(expand=True, fill='both', padx=10, pady=10)

        history = tracker.get_price_history(url)
        if history:
            dates = [datetime.strptime(h[0], '%Y-%m-%d %H:%M:%S') for h in history]
            prices = [h[1] for h in history]

            ax.plot(dates, prices, 'bo-', markersize=6, linewidth=2, label='Price')
            ax.grid(True, linestyle='--', alpha=0.7)
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'₺{x:,.2f}'))
            plt.xticks(rotation=45, ha='right')
            ax.set_title('Price History', pad=20, fontsize=12, fontweight='bold')
            ax.set_xlabel('Date', labelpad=10)
            ax.set_ylabel('Price (TRY)', labelpad=10)
            ax.legend()

            min_price = min(prices)
            max_price = max(prices)
            ax.axhline(y=min_price, color='g', linestyle='--', alpha=0.5)
            ax.axhline(y=max_price, color='r', linestyle='--', alpha=0.5)

            for date, price in zip(dates, prices):
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

        plt.tight_layout()
        canvas.draw()

def main():
    # Use memory_profiler to monitor main function's memory usage
    mem_usage = memory_usage((run_app, ), interval=1, timeout=None)
    print(f"Maximum memory usage: {max(mem_usage):.2f} MB")

def run_app():
    app = PriceTrackerGUI()
    app.mainloop()

if __name__ == "__main__":
    main()