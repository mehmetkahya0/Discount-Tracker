# Price Tracker v1.0

![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)

[![HitCount](https://hits.dwyl.com/mehmetkahya0/Discount-Tracker.svg?style=flat-square)](http://hits.dwyl.com/mehmetkahya0/Discount-Tracker)

A powerful and modern GUI application to monitor and track product prices on popular e-commerce platforms. Get notified when prices drop below your target thresholds!

## 🚀 Features

- **Support for Multiple Sites:** Track prices from [Amazon.com.tr](https://www.amazon.com.tr), [Trendyol](https://www.trendyol.com), [Hepsiburada](https://www.hepsiburada.com), and other websites!
- **Modern UI/UX:** Sleek and responsive interface using `ttkthemes` for a contemporary look.
- **Theme Selection:** Choose from various themes within the application to suit your preference.
- **Price History Graphs:** Visualize the price changes over time with interactive graphs.
- **Resource Monitoring:** Optional CPU and RAM usage display to monitor application performance.
- **Notifications:** Receive alerts when prices drop below your specified thresholds.
- **Data Export:** Export your tracked products and prices to a CSV file.
- **Search Functionality:** Quickly find products in your list with the integrated search bar.

## 🖥️ Screenshots

- **Main Window:** Main application window with modern theme and ASCII art logo.
- **Price History:** Interactive price history graph with zoom and pan capabilities.

## 📦 Installation
### Prerequisites

- Python 3.6 or higher
- `pip` package manager

### Clone the Repository

```bash
git clone https://github.com/mehmetkahya0/price-tracker.git
cd price-tracker
```

## 🔧 Usage
```python
python main.py
```

### Adding a Product
1. Click the "Add Product" button.
2. Enter the URL of the product page.
3. Set your Target Price (Threshold).
4. Click "Add".

### Viewing Price History
1. Select a product from the list.
2. Click "Show Price History" to view the graph.

### Changing Themes
-  Use the "Select Theme" dropdown at the top to choose your preferred theme.

### Exporting Data
- Click "Export CSV" to save your tracked products and prices.


## 🎛️ Configuration
The application uses a config.json file to store product URLs and thresholds.

**Example config.json:**
```json
{
    "products": [
        {
            "url": "https://www.example.com/product",
            "threshold": 1000.0
        }
    ]
}
```
*Note: The application manages this file automatically when you add or remove products through the GUI.*

## ⚙️ Advanced Features
- Resource Monitoring
Enable "Resource Monitoring" to display CPU and RAM usage.

## Search Products
- Use the search bar to filter products by name.


## High DPI Scaling (Windows)
The application automatically handles high DPI scaling on Windows machines.

## 📝 Notes
Ensure internet connectivity for fetching product data.

The application updates prices every 5 minutes by default.


## 📖 License
This project is licensed under the MIT License.

## 🙏 Acknowledgements
Developed by Mehmet Kahya.
GitHub: github.com/mehmetkahya0

## 📧 Contact
For any inquiries or support, please contact mehmetkahyakas5@gmail.com

--------------------------------------------
*Happy tracking and may your desired prices come sooner than expected!*