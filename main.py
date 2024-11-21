# main.py
import tkinter as tk
from ttkthemes import ThemedTk
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
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import webbrowser
import csv
import psutil

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
            'Accept': ('text/html,application/xhtml+xml,application/xml;'
                       'q=0.9,*/*;q=0.8'),
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
        },
        'trendyol': {
            'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
                           ' Chrome/120.0.0.0'),
            'Accept': ('text/html,application/xhtml+xml,application/xml;'
                       'q=0.9,*/*;q=0.8'),
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
        },
        'temu': {
            'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
                           ' AppleWebKit/537.36 (KHTML, like Gecko)'
                           ' Chrome/91.0.4472.124 Safari/537.36'),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
        },
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
        },
        'temu': {
            'price': ['span.product-price__current-price'],
            'title': 'h1.product-title__title'
        },
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
        elif 'temu' in url:
            return 'temu'
        return 'amazon'  # Default to Amazon

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

    def track_product(self, product: ProductConfig) -> Optional[float]:
        site_type = self.get_site_type(product.url)
        try:
            response = self.session.get(
                product.url,
                headers=self.HEADERS[site_type],
                timeout=10  # Adjusted timeout
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
            short_name = f"{product.name[:30]}..." if len(
                product.name) > 30 else product.name
            message = f"""
💰 Current Price: ₺{price:.2f}
🎯 Target Price: ₺{product.threshold:.2f}
📊 Savings: ₺{product.threshold - price:.2f}

{product.url}
"""
            MB_ICONINFORMATION = 0x40

            ctypes.windll.user32.MessageBoxW(
                0, message, f"Price Drop! - {short_name}", MB_ICONINFORMATION
            )
            ctypes.windll.kernel32.Beep(1000, 500)  # Beep sound

            logging.info(f"Notification sent for {short_name}")
        except Exception as e:
            logging.error(f"Notification failed: {str(e)}")


class PriceTrackerGUI:
    def __init__(self):
        # Use default theme 'arc'
        self.root = ThemedTk(theme="arc")
        self.root.title("Price Tracker v1.0")
        self.root.geometry("1500x700")
        self.tracker = PriceTracker()
        self.products_data = []  # Initialize products data list
        # Variable to control monitoring
        self.monitoring = tk.BooleanVar(value=False)
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(expand=True, fill='both', padx=10, pady=10)
        self.create_theme_option()  # Add theme selection option
        self.create_table()
        self.create_controls()
        self.create_resource_usage_label()
        self.after_id = self.root.after(
            0, self.update_prices)  # Immediate update

        # ASCII Logo
        logo_text = """
█▀█ █▀█ █ █▀▀ █▀▀   ▀█▀ █▀█ ▄▀█ █▀▀ █▄▀ █▀▀ █▀█
█▀▀ █▀▄ █ █▄▄ ██▄    █  █▀▄ █▀█ █▄▄ █ █ ██▄ █▀▄"""
        style = ttk.Style()
        style.configure("Green.TLabel", foreground="green",
                        font=("Consolas", 10, "bold"))

        ttk.Label(
            self.main_frame,
            text=logo_text,
            style="Green.TLabel",
            justify='center'
        ).pack(pady=(10, 20))

        self.root.mainloop()

    def create_theme_option(self):
        theme_frame = ttk.Frame(self.main_frame)
        theme_frame.pack(fill='x', pady=(5, 5))

        ttk.Label(theme_frame, text="Select Theme:").pack(
            side='left', padx=(5, 5))
        self.theme_var = tk.StringVar(value='arc')

        themes = sorted(self.root.get_themes())
        self.theme_menu = ttk.OptionMenu(
            theme_frame,
            self.theme_var,
            self.theme_var.get(),
            *themes,
            command=self.change_theme
        )
        self.theme_menu.pack(side='left')

    def change_theme(self, theme_name):
        self.root.set_theme(theme_name)

    def create_resource_usage_label(self):
        resource_frame = ttk.Frame(self.main_frame)
        resource_frame.pack(pady=(5, 5), fill='x')

        self.monitor_checkbox = ttk.Checkbutton(
            resource_frame,
            text="Enable Resource Monitoring",
            variable=self.monitoring,
            command=self.toggle_resource_monitoring
        )
        self.monitor_checkbox.pack(side='left')

        self.resource_label = ttk.Label(
            resource_frame, text="", font=("Helvetica", 10))
        self.resource_label.pack(side='left', padx=(10, 0))

    def toggle_resource_monitoring(self):
        if self.monitoring.get():
            self.update_resource_usage()
        else:
            self.resource_label.config(text="")

    def update_resource_usage(self):
        if self.monitoring.get():
            process = psutil.Process()
            ram_usage = process.memory_info().rss / (1024 * 1024)
            cpu_usage = process.cpu_percent(interval=0)

            self.resource_label.config(
                text=f"CPU Usage: {cpu_usage:.1f}%   RAM Usage: {
                    ram_usage:.1f} MB"
            )
            self.root.after(1000, self.update_resource_usage)
        else:
            self.resource_label.config(text="")

    def create_table(self):
        style = ttk.Style()
        style.configure("Treeview.Heading", font=("Helvetica", 10, "bold"))
        style.configure("Treeview", font=("Helvetica", 10))

        columns = ('Product', 'Current Price',
                   'Target', 'Site', 'Status', 'URL')
        self.tree = ttk.Treeview(
            self.main_frame, columns=columns, show='headings', style="Treeview"
        )

        self.tree['displaycolumns'] = columns[:-1]  # Exclude URL from display

        for col in columns[:-1]:  # Exclude URL
            self.tree.heading(col, text=col)
            self.tree.column(col, width=150, anchor='center')

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
        left_frame.pack(side='left', padx=5)

        ttk.Button(
            left_frame, text="Add Product",
            command=self.add_product
        ).pack(side='left', padx=5, pady=5)

        ttk.Button(
            left_frame, text="Remove Product",
            command=self.remove_product
        ).pack(side='left', padx=5, pady=5)

        ttk.Button(
            left_frame, text="Change Threshold",
            command=self.change_threshold
        ).pack(side='left', padx=5, pady=5)

        ttk.Button(
            left_frame, text="Show Price History",
            command=self.show_history
        ).pack(side='left', padx=5, pady=5)

        ttk.Button(
            left_frame, text="Go to Product",
            command=self.go_to_product
        ).pack(side='left', padx=5, pady=5)

        ttk.Button(
            left_frame, text="🔄 Refresh",
            command=self.update_prices
        ).pack(side='left', padx=5, pady=5)

        # Middle frame for search
        middle_frame = ttk.Frame(control_frame)
        middle_frame.pack(side='left', padx=20, fill='x', expand=True)

        self.search_var = tk.StringVar()
        self.search_var.trace('w', self.on_search_change)

        self.search_entry = ttk.Entry(
            middle_frame, textvariable=self.search_var, font=("Helvetica", 10)
        )
        self.search_entry.pack(side='left', fill='x', expand=True)

        # Add placeholder behavior
        self.search_entry.insert(0, "Search products...")
        self.search_entry.bind('<FocusIn>', self._on_search_focus_in)
        self.search_entry.bind('<FocusOut>', self._on_search_focus_out)

        # Right side buttons
        right_frame = ttk.Frame(control_frame)
        right_frame.pack(side='right', padx=5)

        ttk.Button(
            right_frame, text="Export CSV",
            command=self.export_csv
        ).pack(side='right', padx=5, pady=5)

        ttk.Button(
            right_frame, text="Info",
            command=self.info
        ).pack(side='right', padx=5, pady=5)

        ttk.Button(
            right_frame, text="Quit",
            command=self.root.quit
        ).pack(side='right', padx=5, pady=5)

    def _on_search_focus_in(self, event):
        if self.search_entry.get() == "Search products...":
            self.search_entry.delete(0, tk.END)

    def _on_search_focus_out(self, event):
        if not self.search_entry.get():
            self.search_entry.insert(0, "Search products...")

    def on_search_change(self, *args):
        search_text = self.search_var.get().lower()

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
        self.after_id = self.root.after(
            300000, self.update_prices)  # Update every 5 minutes

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
        dialog = AddProductDialog(self.root)
        self.root.wait_window(dialog.top)
        self.update_prices()

    def remove_product(self):
        selected = self.tree.selection()
        if selected:
            if messagebox.askyesno("Confirm", "Remove selected product?"):
                item = self.tree.item(selected[0])
                url = item['values'][5]  # URL is in hidden column

                with open('config.json', 'r+', encoding='utf-8') as f:
                    config = json.load(f)
                    config['products'] = [
                        p for p in config['products'] if p['url'] != url]
                    f.seek(0)
                    json.dump(config, f, indent=4)
                    f.truncate()

                self.tree.delete(selected)
                self.update_prices()

    def change_threshold(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning(
                "Warning", "Please select a product to change its threshold.")
            return

        item = self.tree.item(selected[0])
        url = item['values'][5]
        current_threshold_str = item['values'][2]  # e.g., '₺123.45'

        try:
            # Extract numeric value from the threshold string
            current_threshold = float(
                current_threshold_str.replace('₺', '').replace(',', '.'))
        except ValueError:
            messagebox.showerror("Error", "Invalid threshold format.")
            return

        dialog = ChangeThresholdDialog(self.root, current_threshold)
        self.root.wait_window(dialog.top)

        if dialog.new_threshold is not None:
            try:
                new_threshold = float(dialog.new_threshold.replace(',', '.'))
                if new_threshold <= 0:
                    raise ValueError

                with open('config.json', 'r+', encoding='utf-8') as f:
                    config = json.load(f)
                    for product in config['products']:
                        if product['url'] == url:
                            product['threshold'] = new_threshold
                            break
                    f.seek(0)
                    json.dump(config, f, indent=4)
                    f.truncate()

                self.update_prices()
                messagebox.showinfo(
                    "Success", "Threshold updated successfully.")

            except ValueError:
                messagebox.showerror(
                    "Error", "Please enter a valid positive number for threshold.")
            except Exception as e:
                messagebox.showerror(
                    "Error", f"Failed to update threshold: {str(e)}")

    def show_history(self):
        selected = self.tree.selection()
        if selected:
            item = self.tree.item(selected[0])
            url = item['values'][5]  # URL is in hidden column
            HistoryDialog(self.root, url, self.tracker)

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
            try:
                with open(filename, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(
                        ['Product', 'Current Price', 'Target', 'Site', 'Status'])
                    for item in self.tree.get_children():
                        values = self.tree.item(item)['values']
                        writer.writerow(values[:-1])  # Exclude URL
                messagebox.showinfo(
                    "Export CSV", f"Data exported to {filename}")
            except Exception as e:
                messagebox.showerror(
                    "Error", f"Failed to export CSV: {str(e)}")

    def info(self):
        about = tk.Toplevel(self.root)
        about.title("About Price Tracker")
        about.geometry("600x400")
        about.resizable(False, False)

        # Center window
        about.transient(self.root)
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
        logo = ttk.Label(main_frame, text=logo_text,
                         style="Green.TLabel", justify='center')
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

        for site in ["Amazon.com.tr", "Trendyol", "Hepsiburada", "Temu"]:
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
        github_link.bind(
            "<Button-1>", lambda e: webbrowser.open("https://github.com/mehmetkahya0"))

        # Close button
        ttk.Button(
            main_frame,
            text="Close",
            command=about.destroy
        ).pack(pady=(20, 0))


class AddProductDialog:
    def __init__(self, parent):
        self.top = tk.Toplevel(parent)
        self.top.title("Add Product")
        self.top.geometry("500x150")
        self.top.resizable(False, False)

        ttk.Label(self.top, text="URL:").grid(
            row=0, column=0, padx=10, pady=10, sticky='e')
        self.url = ttk.Entry(self.top, width=60)
        self.url.grid(row=0, column=1, padx=10, pady=10)

        ttk.Label(self.top, text="Threshold (₺):").grid(
            row=1, column=0, padx=10, pady=10, sticky='e')
        self.threshold = ttk.Entry(self.top, width=20)
        self.threshold.grid(row=1, column=1, padx=10, pady=10, sticky='w')

        ttk.Button(self.top, text="Add", command=self.add).grid(
            row=2, column=0, columnspan=2, pady=10
        )

        self.url.focus_set()

    def add(self):
        try:
            url = self.url.get().strip()
            threshold = self.threshold.get().strip()

            if not url:
                messagebox.showerror("Error", "URL cannot be empty")
                return

            if not threshold:
                messagebox.showerror("Error", "Threshold cannot be empty")
                return

            threshold_value = float(threshold.replace(',', '.'))
            if threshold_value <= 0:
                raise ValueError

            with open('config.json', 'r+', encoding='utf-8') as f:
                config = json.load(f)
                # Check if product already exists
                if any(p['url'] == url for p in config['products']):
                    messagebox.showwarning("Warning", "Product already exists")
                    return

                config['products'].append({
                    'url': url,
                    'threshold': threshold_value
                })
                f.seek(0)
                json.dump(config, f, indent=4)
                f.truncate()

            self.top.destroy()
        except ValueError:
            messagebox.showerror(
                "Error", "Please enter a valid positive number for threshold.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to add product: {str(e)}")


class ChangeThresholdDialog:
    def __init__(self, parent, current_threshold):
        self.new_threshold = None
        self.top = tk.Toplevel(parent)
        self.top.title("Change Threshold")
        self.top.geometry("400x150")
        self.top.resizable(False, False)

        ttk.Label(self.top, text=f"Current Threshold: ₺{
                  current_threshold:.2f}").pack(pady=10)

        ttk.Label(self.top, text="New Threshold (₺):").pack(pady=5)
        self.threshold_var = tk.StringVar()
        self.entry = ttk.Entry(
            self.top, textvariable=self.threshold_var, width=30)
        self.entry.pack(pady=5)
        self.entry.focus_set()

        ttk.Button(self.top, text="Save", command=self.save).pack(pady=10)

    def save(self):
        threshold = self.threshold_var.get().strip()
        if not threshold:
            messagebox.showerror("Error", "Threshold cannot be empty.")
            return
        try:
            self.new_threshold = float(threshold.replace(',', '.'))
            if self.new_threshold <= 0:
                raise ValueError
            self.top.destroy()
        except ValueError:
            messagebox.showerror(
                "Error", "Please enter a valid positive number for threshold.")


class HistoryDialog:
    def __init__(self, parent, url, tracker):
        self.top = tk.Toplevel(parent)
        self.top.title("Price History")
        self.top.geometry("800x600")
        self.top.resizable(True, True)

        fig, ax = plt.subplots(figsize=(8, 5))
        canvas = FigureCanvasTkAgg(fig, master=self.top)

        # Add toolbar for zoom and pan
        toolbar = NavigationToolbar2Tk(canvas, self.top)
        toolbar.update()
        canvas.get_tk_widget().pack(expand=True, fill='both')

        history = tracker.get_price_history(url)
        if history:
            dates = [datetime.strptime(h[0], '%Y-%m-%d %H:%M:%S')
                     for h in history]
            prices = [h[1] for h in history]

            ax.plot(dates, prices, marker='o', linestyle='-',
                    color='#1f77b4', label='Price')
            ax.fill_between(dates, prices, color='#AED6F1', alpha=0.5)
            ax.grid(True, linestyle='--', alpha=0.7)
            ax.yaxis.set_major_formatter(
                plt.FuncFormatter(lambda x, p: f'₺{x:,.2f}'))
            plt.setp(ax.get_xticklabels(), rotation=45, ha='right')
            ax.set_title('Price History', pad=20,
                         fontsize=14, fontweight='bold')
            ax.set_xlabel('Date', fontsize=12)
            ax.set_ylabel('Price (TRY)', fontsize=12)
            ax.legend()

            min_price = min(prices)
            max_price = max(prices)
            ax.axhline(y=min_price, color='green', linestyle='--',
                       alpha=0.5, label='Min Price')
            ax.axhline(y=max_price, color='red', linestyle='--',
                       alpha=0.5, label='Max Price')
            ax.legend()

        else:
            ax.text(0.5, 0.5, 'No price history available',
                    horizontalalignment='center',
                    verticalalignment='center',
                    transform=ax.transAxes,
                    fontsize=12, color='gray')

        plt.tight_layout()
        canvas.draw()


def main():
    app = PriceTrackerGUI()


if __name__ == "__main__":
    main()
