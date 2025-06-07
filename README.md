# AutoShopify API - VPS Deployment Guide

This guide explains how to deploy the AutoShopify API on your VPS so it runs in the background even after you logout.

## 📋 Prerequisites

- Linux VPS (Ubuntu/Debian/CentOS)
- Python 3.7+ (will be auto-installed if missing)
- Root or sudo access

## 🚀 **SUPER QUICK SETUP** (One-Command Installation)

### Fresh VPS? Just run this:
```bash
# Upload all files to your VPS and run:
chmod +x install_vps.sh
./install_vps.sh
```

**That's it!** The script will:
- ✅ Update your system
- ✅ Install Python3 and all dependencies
- ✅ Start the API server automatically
- ✅ Run in background (survives logout)

## 🚀 Quick Setup (Method 1: Using Scripts)

### 1. Upload Files to VPS
```bash
# Create directory
sudo mkdir -p /opt/autoshopify
cd /opt/autoshopify

# Upload your files:
# - autoshopify.py
# - start_daemon.sh
# - stop_daemon.sh
# - install_vps.sh
# - addresses.txt (if you have it)
```

### 2. Auto-Install Dependencies (NEW!)
```bash
# Method A: Use the all-in-one installer
chmod +x install_vps.sh
./install_vps.sh

# Method B: Use the smart startup script
chmod +x start_daemon.sh
./start_daemon.sh  # Will auto-install dependencies on first run

# Method C: Manual dependency installation
python3 autoshopify.py --install-deps  # Install Python packages
python3 autoshopify.py --install-system-deps  # Install system packages (needs sudo)
```

### 3. Start the Server
```bash
# Start with default settings (port 6902)
./start_daemon.sh

# Or start with custom port and shutdown key
./start_daemon.sh 8080 "my_secret_key_123"

# Force reinstall dependencies
./start_daemon.sh 6902 "my_key" --install-deps
```

### 4. Verify Server is Running
```bash
# Check health
curl http://localhost:6902/health

# Check your API endpoint
curl "http://localhost:6902/shauto?lista=4111111111111111|12|2025|123&siteurl=https://example-shop.myshopify.com"
```

### 5. Stop the Server
```bash
# Using the stop script
./stop_daemon.sh

# Or with custom shutdown key
./stop_daemon.sh "my_secret_key_123" 8080
```

## 🔧 Manual Dependency Installation (If Needed)

### Install System Dependencies
```bash
# Ubuntu/Debian
sudo apt update && sudo apt install -y python3 python3-pip python3-dev curl lsof net-tools

# CentOS/RHEL
sudo yum install -y python3 python3-pip python3-devel curl lsof net-tools

# Or let the script do it
python3 autoshopify.py --install-system-deps
```

### Install Python Dependencies
```bash
# Manual installation
pip3 install flask requests beautifulsoup4 brotli urllib3

# Or use the auto-installer
python3 autoshopify.py --install-deps
```

## 🔧 Advanced Setup (Method 2: SystemD Service)

For production environments, use systemd for better process management:

### 1. Create Service File
```bash
sudo cp autoshopify.service /etc/systemd/system/
sudo nano /etc/systemd/system/autoshopify.service
```

### 2. Edit Service Configuration
Update the following in the service file:
- `WorkingDirectory`: Path to your script directory
- `ExecStart`: Path to your Python and script
- `User/Group`: Appropriate user (create if needed)
- `Environment=SHUTDOWN_KEY`: Your secure shutdown key

### 3. Enable and Start Service
```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service (start on boot)
sudo systemctl enable autoshopify

# Start service
sudo systemctl start autoshopify

# Check status
sudo systemctl status autoshopify
```

### 4. Manage Service
```bash
# Start
sudo systemctl start autoshopify

# Stop  
sudo systemctl stop autoshopify

# Restart
sudo systemctl restart autoshopify

# View logs
sudo journalctl -u autoshopify -f

# Disable auto-start
sudo systemctl disable autoshopify
```

## 🛠 Manual Setup (Method 3: Direct Commands)

### Using nohup (Simple)
```bash
# Start in background
nohup python3 autoshopify.py --daemon --port 6902 > logs/autoshopify.log 2>&1 &

# Get process ID
echo $! > autoshopify.pid

# Stop server
kill $(cat autoshopify.pid)
```

### Using screen (Detachable Session)
```bash
# Install screen
sudo apt install screen -y

# Start new screen session
screen -S autoshopify

# Run your server
python3 autoshopify.py --daemon --port 6902

# Detach: Press Ctrl+A then D
# Reattach later: screen -r autoshopify
# Kill session: screen -X -S autoshopify quit
```

### Using tmux (Alternative to screen)
```bash
# Install tmux
sudo apt install tmux -y

# Start new tmux session
tmux new-session -d -s autoshopify

# Run command in session
tmux send-keys -t autoshopify 'python3 autoshopify.py --daemon --port 6902' Enter

# Attach to session: tmux attach -t autoshopify
# Kill session: tmux kill-session -t autoshopify
```

## 📊 Monitoring & Logs

### Log Files (when using --daemon)
```bash
# Main application logs
tail -f logs/autoshopify.log

# Error logs only
tail -f logs/autoshopify_error.log

# Startup logs (when using scripts)
tail -f logs/startup.log
```

### Check Server Status
```bash
# Health check
curl http://localhost:6902/health

# Check if process is running
ps aux | grep autoshopify

# Check port usage
netstat -tlnp | grep 6902
# or
lsof -i :6902
```

### Resource Monitoring
```bash
# Monitor system resources
htop

# Monitor specific process
top -p $(cat autoshopify.pid)

# Check disk space
df -h

# Check memory usage
free -h
```

## 🎯 New Command Line Options

The updated script now supports these new options:

```bash
python3 autoshopify.py --help

Options:
  --daemon                    Run as daemon in background
  --host HOST                 Host to bind to (default: 0.0.0.0)
  --port PORT                 Port to bind to (default: 6902)
  --debug                     Enable debug mode
  --install-deps              Force install Python dependencies
  --install-system-deps       Install system dependencies (requires sudo)
```

## 🔐 Security Considerations

### 1. Firewall Configuration
```bash
# Allow your API port (example: 6902)
sudo ufw allow 6902/tcp

# For external access (be careful!)
sudo ufw allow from any to any port 6902

# Check status
sudo ufw status
```

### 2. Reverse Proxy (Recommended)
Use Nginx as reverse proxy for better security:

```nginx
# /etc/nginx/sites-available/autoshopify
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://localhost:6902;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

### 3. SSL Certificate (Let's Encrypt)
```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx -y

# Get certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal
sudo certbot renew --dry-run
```

## 🔧 Troubleshooting

### Common Issues

1. **Permission Denied**
   ```bash
   sudo chown -R $USER:$USER /opt/autoshopify
   chmod +x *.sh
   ```

2. **Port Already in Use**
   ```bash
   # Find process using port
   lsof -i :6902
   
   # Kill process
   sudo kill -9 <PID>
   ```

3. **Python Module Not Found**
   ```bash
   # Use auto-installer
   python3 autoshopify.py --install-deps
   
   # Or install manually
   pip3 install flask requests beautifulsoup4 brotli
   ```

4. **Server Not Responding**
   ```bash
   # Check logs
   tail -f logs/autoshopify_error.log
   
   # Check if process is running
   ps aux | grep python
   ```

### Log Analysis
```bash
# Search for errors
grep -i error logs/autoshopify.log

# Search for specific patterns
grep "CHARGED\|DECLINED" logs/autoshopify.log

# Monitor real-time
tail -f logs/autoshopify.log | grep -E "(CHARGED|DECLINED|ERROR)"
```

## 📱 API Usage

Once deployed, use your API:

```bash
# Health check
curl http://your-server-ip:6902/health

# Test endpoint
curl "http://your-server-ip:6902/shauto?lista=4111111111111111|12|2025|123&siteurl=https://shop.example.com"

# With proxy
curl "http://your-server-ip:6902/shauto?lista=4111111111111111|12|2025|123&siteurl=https://shop.example.com&proxy=proxy.com:8080:user:pass"
```

## 🛡 Security Best Practices

1. **Change Default Shutdown Key**
   ```bash
   export SHUTDOWN_KEY="your_very_secure_key_here"
   ```

2. **Restrict API Access**
   - Use firewall rules to limit IP access
   - Implement rate limiting
   - Use API keys for authentication

3. **Regular Updates**
   ```bash
   # Update system packages
   sudo apt update && sudo apt upgrade -y
   
   # Update Python packages
   pip3 list --outdated
   pip3 install --upgrade package_name
   ```

4. **Backup Configuration**
   ```bash
   # Backup your setup
   tar -czf autoshopify_backup.tar.gz /opt/autoshopify/
   ```

## 🎉 Quick Commands Summary

```bash
# One-command setup on fresh VPS
./install_vps.sh

# Start server with auto-dependency installation
./start_daemon.sh

# Start with custom settings
./start_daemon.sh 8080 "my_secret_key"

# Stop server
./stop_daemon.sh

# Check status
curl http://localhost:6902/health

# View logs
tail -f logs/autoshopify.log

# Force reinstall dependencies
python3 autoshopify.py --install-deps
```

## 📞 Support

If you encounter issues:

1. Check the logs first
2. Use the auto-installer: `python3 autoshopify.py --install-deps`
3. Verify all dependencies are installed
4. Ensure proper file permissions
5. Check firewall settings
6. Monitor system resources

---

**Author**: Shubham (TheRam_Bhakt)  
**Version**: 2.0 (Now with Auto-Installation!)  
**Last Updated**: 2024 
