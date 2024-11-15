# test_price_tracker.py

import pytest
from unittest.mock import Mock, patch
import json
from bs4 import BeautifulSoup
from main import PriceTracker, ProductConfig
from datetime import datetime

@pytest.fixture
def test_config():
    return {
        "products": [
            {
                "url": "https://www.amazon.com.tr/STANLEY-Quick-Paslanmaz-Termos-Turuncu/dp/B0CNTW2G2F/?_encoding=UTF8&ref_=pd_hp_d_atf_ci_mcx_mr_ca_hp_atf_d",
                "threshold": 1000.0,
                "name": "Test Product"
            }
        ]
    }

@pytest.fixture
def tracker(tmp_path, test_config):
    config_file = tmp_path / "test_config.json"
    config_file.write_text(json.dumps(test_config))
    return PriceTracker(str(config_file))

@pytest.fixture
def mock_response():
    mock = Mock()
    mock.content = """
        <span class="a-price-whole">1.299</span>
        <span id="productTitle">Test Product</span>
    """
    return mock

def test_load_config(tracker, test_config):
    assert tracker.config == test_config

def test_extract_price_amazon(tracker):
    html = '<span class="a-price-whole">1.299</span>'
    soup = BeautifulSoup(html, 'html.parser')
    price = tracker.extract_price(soup, 'amazon')
    assert price == 1299.0

def test_extract_price_trendyol(tracker):
    html = '<span class="prc-dsc">1.299,99 TL</span>'
    soup = BeautifulSoup(html, 'html.parser')
    price = tracker.extract_price(soup, 'trendyol')
    assert price == 1299.99

def test_extract_price_hepsiburada(tracker):
    html = '<span data-test-id="price-current-price">1.299,99 TL</span>'
    soup = BeautifulSoup(html, 'html.parser')
    price = tracker.extract_price(soup, 'hepsiburada')
    assert price == 1299.99

@patch('requests.Session')
def test_track_product(mock_session, tracker, mock_response):
    mock_session.return_value.get.return_value = mock_response
    
    product = ProductConfig(
        url="https://www.amazon.com.tr/STANLEY-Quick-Paslanmaz-Termos-Turuncu/dp/B0CNTW2G2F/?_encoding=UTF8&ref_=pd_hp_d_atf_ci_mcx_mr_ca_hp_atf_d",
        threshold=2000.0,
        name="Test Product"
    )
    
    price = tracker.track_product(product)
    assert price == 1299.0
    assert product.last_price == 1299.0
    assert isinstance(product.last_check, datetime)

@patch('plyer.notification.notify')
def test_send_notification(mock_notify, tracker):
    product = ProductConfig(
        url="https://test.com",
        threshold=2000.0,
        name="Test Product"
    )
    
    tracker.send_notification(product, 1500.0)
    mock_notify.assert_called_once()

def test_get_site_type(tracker):
    assert tracker.get_site_type("https://www.amazon.com.tr/test") == "amazon"
    assert tracker.get_site_type("https://www.trendyol.com/test") == "trendyol"
    assert tracker.get_site_type("https://www.hepsiburada.com/test") == "hepsiburada"
    assert tracker.get_site_type("https://unknown.com/test") == "amazon"

@patch('requests.Session')
def test_main_loop(mock_session, tracker, mock_response, capsys):
    mock_session.return_value.get.return_value = mock_response
    
    with patch('time.sleep'):  # Don't actually sleep in tests
        with pytest.raises(KeyboardInterrupt):
            tracker.main()
    
    captured = capsys.readouterr()
    assert "Price Tracker" in captured.out
    assert "Checking:" in captured.out