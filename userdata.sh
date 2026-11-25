#!/bin/bash
command -v python3 >/dev/null || dnf install -y python3
mkdir -p /srv/www && cd /srv/www
ID=$(curl -s -m 2 http://169.254.169.254/latest/meta-data/instance-id || hostname)
echo "<h1>AgendaSaude RP</h1><p>Atendido por: $ID</p>" > index.html
echo ok > health
setsid nohup python3 -m http.server 80 >/var/log/web.log 2>&1 &
