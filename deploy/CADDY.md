# Caddy in front of the API

Uvicorn stays on **127.0.0.1:8080**. Caddy terminates HTTPS and proxies.

## 1. DNS

Create an **A record**:

```text
api.yourdomain.com  →  YOUR_VPS_PUBLIC_IP
```

Wait until it resolves (`dig +short api.yourdomain.com`).

## 2. Install Caddy (Ubuntu)

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy
```

## 3. Config

```bash
cd ~/TurnaroundIQ && git pull
sudo mkdir -p /var/log/caddy
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo nano /etc/caddy/Caddyfile   # change api.yourdomain.com
```

## 4. API still local-only

```bash
# uvicorn must be:
uvicorn api.app:app --host 127.0.0.1 --port 8080
```

Do **not** use `--host 0.0.0.0` once Caddy is live.

## 5. Start

```bash
sudo systemctl enable --now caddy
sudo systemctl reload caddy
sudo systemctl status caddy
```

Caddy obtains Let’s Encrypt certs automatically (ports **80** and **443** must be open).

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw delete allow 8080/tcp   # if you opened 8080 for testing
```

## 6. Test

```bash
curl -s https://api.yourdomain.com/health
curl -s -H "Authorization: Bearer test" https://api.yourdomain.com/me
```

## 7. RevenueCat webhook

```text
https://api.yourdomain.com/webhooks/revenuecat
```

Authorization header = `REVENUECAT_WEBHOOK_AUTH`.

## 8. App base URL

```text
https://api.yourdomain.com
```

## Troubleshooting

| Symptom | Check |
|--------|--------|
| Certificate errors | DNS not pointing here yet; wait and `journalctl -u caddy -f` |
| 502 Bad Gateway | uvicorn not running on 127.0.0.1:8080 |
| Connection refused | ufw / cloud firewall blocking 80/443 |
