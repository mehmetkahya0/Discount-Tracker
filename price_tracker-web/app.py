# app.py
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import logging
from config import Config
from urllib.parse import urlparse

app = Flask(__name__)
app.config.from_object(Config)
db = SQLAlchemy(app)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='price_tracker.log'
)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(500), unique=True, nullable=False)
    threshold = db.Column(db.Float, nullable=False)
    current_price = db.Column(db.Float)
    last_check = db.Column(db.DateTime, default=datetime.utcnow)
    histories = db.relationship('PriceHistory', backref='product', lazy=True)

class PriceHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    price = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
        
def extract_price(url: str, soup: BeautifulSoup) -> float:
    site_type = get_site_type(url)
    selectors = {
        'amazon': ['span.a-price-whole', 'span#priceblock_ourprice', 'span#price_inside_buybox'],
        'trendyol': ['span.prc-dsc', 'span.product-price'],
        'hepsiburada': ['span[data-bind="markupText: currentPriceBeforePoint"]']
    }
    
    for selector in selectors.get(site_type, []):
        element = soup.select_one(selector)
        if element:
            price_text = element.text.strip()
            return float(price_text.replace('TL', '').replace('₺', '').replace('.', '').replace(',', '.'))
    raise ValueError("Could not extract price")

def get_site_type(url: str) -> str:
    domain = urlparse(url).netloc
    if 'amazon' in domain:
        return 'amazon'
    elif 'trendyol' in domain:
        return 'trendyol'
    elif 'hepsiburada' in domain:
        return 'hepsiburada'
    return 'unknown'

@app.route('/')
def index():
    products = Product.query.all()
    return render_template('index.html', products=products)

@app.route('/add_product', methods=['POST'])
def add_product():
    try:
        url = request.form.get('url')
        threshold = request.form.get('threshold')

        if not url or not threshold:
            flash('URL and threshold are required', 'error')
            return redirect(url_for('index'))

        try:
            threshold = float(threshold)
        except ValueError:
            flash('Invalid threshold value', 'error')
            return redirect(url_for('index'))

        headers = {'User-Agent': app.config['USER_AGENTS']['default']}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        price = extract_price(url, soup)
        
        # Extract product name
        site_type = get_site_type(url)
        name_selectors = {
            'amazon': '#productTitle',
            'trendyol': 'h1.pr-new-br',
            'hepsiburada': 'h1.product-name'
        }
        name_element = soup.select_one(name_selectors.get(site_type, 'h1'))
        name = name_element.text.strip() if name_element else 'Unknown Product'

        product = Product(name=name, url=url, threshold=threshold, current_price=price)
        db.session.add(product)
        db.session.flush()

        # Add initial price history
        history = PriceHistory(product_id=product.id, price=price)
        db.session.add(history)
        db.session.commit()

        flash('Product added successfully', 'success')
        
    except requests.RequestException as e:
        flash(f'Error accessing URL: {str(e)}', 'error')
    except Exception as e:
        flash(f'Error adding product: {str(e)}', 'error')
        db.session.rollback()
        logging.error(f'Error adding product: {str(e)}')

    return redirect(url_for('index'))

@app.route('/history/<int:product_id>')
def price_history(product_id):
    product = Product.query.get_or_404(product_id)
    history = PriceHistory.query.filter_by(product_id=product_id).order_by(PriceHistory.timestamp).all()
    
    # Pre-format timestamps and collect prices
    timestamps = [entry.timestamp.strftime('%Y-%m-%d %H:%M:%S') for entry in history]
    prices = [entry.price for entry in history]
    
    return render_template('history.html', product=product, history=history, timestamps=timestamps, prices=prices)

@app.route('/remove/<int:product_id>')
def remove_product(product_id):
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    flash('Product removed successfully', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)