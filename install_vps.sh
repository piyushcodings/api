#!/bin/bash

# AutoShopify API - One-Click VPS Installation Script
# Usage: ./install_vps.sh

echo "🚀 AutoShopify API - Fresh VPS Installation"
echo "============================================"

# Update system
echo "📦 Updating system packages..."
if command -v apt-get &> /dev/null; then
    sudo apt-get update && sudo apt-get upgrade -y
    sudo apt-get install -y python3 python3-pip python3-dev python3-setuptools curl lsof net-tools wget unzip
elif command -v yum &> /dev/null; then
    sudo yum update -y
    sudo yum install -y python3 python3-pip python3-devel curl lsof net-tools wget unzip
elif command -v dnf &> /dev/null; then
    sudo dnf update -y
    sudo dnf install -y python3 python3-pip python3-devel curl lsof net-tools wget unzip
else
    echo "❌ Unsupported package manager. Please install dependencies manually."
    exit 1
fi

# Install Python packages globally
echo "🐍 Installing Python packages..."
pip3 install --upgrade pip
pip3 install flask requests beautifulsoup4 brotli urllib3

# Make sure scripts are executable
echo "🔧 Setting up permissions..."
chmod +x *.sh
chmod +x *.py

# Install and start the service
echo "🎯 Starting AutoShopify API..."
if [ -f "start_daemon.sh" ]; then
    ./start_daemon.sh
else
    echo "⚠️ start_daemon.sh not found. Starting manually..."
    python3 autoshopify.py --install-deps --daemon
fi

echo ""
echo "🎉 Installation Complete!"
echo "========================"
echo "Your AutoShopify API is now running in the background!"
echo ""
echo "Quick Test:"
echo "curl http://localhost:6902/health"
echo ""
echo "API Usage:"
echo "curl \"http://your-server-ip:6902/shauto?lista=4111111111111111|12|2025|123&siteurl=https://shop.example.com\""
echo ""
echo "To stop the server:"
echo "./stop_daemon.sh"
echo ""
echo "To view logs:"
echo "tail -f logs/autoshopify.log" 