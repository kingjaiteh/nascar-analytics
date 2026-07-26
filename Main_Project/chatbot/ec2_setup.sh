#!/bin/bash
# Run this once on the EC2 instance to install everything.
set -e

# System packages
sudo dnf update -y
sudo dnf install -y python3 python3-pip nginx git

# App directory
mkdir -p /home/ec2-user/nascar

# Python dependencies
pip3 install --user streamlit plotly pandas duckdb anthropic duckduckgo-search

# nginx config: proxy port 80 → 8501
sudo tee /etc/nginx/conf.d/nascar.conf > /dev/null <<'NGINX'
server {
    listen 80;
    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }
}
NGINX

# Remove default nginx config so it doesn't conflict
sudo rm -f /etc/nginx/conf.d/default.conf

sudo systemctl enable nginx
sudo systemctl restart nginx

# systemd service for Streamlit
sudo tee /etc/systemd/system/nascar.service > /dev/null <<'SERVICE'
[Unit]
Description=NASCAR Analytics Chatbot
After=network.target

[Service]
User=ec2-user
WorkingDirectory=/home/ec2-user/nascar/chatbot
ExecStart=/home/ec2-user/.local/bin/streamlit run app.py --server.port 8501 --server.headless true --server.address 0.0.0.0
Restart=always
RestartSec=5
Environment=AWS_DEFAULT_REGION=us-east-1

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable nascar
echo "Setup complete. Deploy your files then: sudo systemctl start nascar"
