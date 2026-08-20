# Deploy Meter Buddy (compose + `.env` only)

Production stack: **Caddy** (HTTPS / Let’s Encrypt via DuckDNS) + **FastAPI backend** + SQLite volume.

You only need these two files on the Docker host:

- [`docker-compose.yml`](docker-compose.yml)
- [`.env`](.env) (copy from [`.env.example`](.env.example))

No repo clone or local image build is required. Images come from GHCR:

- `ghcr.io/bakroistvan/meter_buddy`
- `ghcr.io/bakroistvan/meter_buddy-caddy`

Make both packages **public**, or run `docker login ghcr.io` before the first pull.

Firmware flash and Home Assistant (HACS) are separate — see [docs/README.md](../docs/README.md) and [custom_components/meter_buddy/README.md](../custom_components/meter_buddy/README.md).

## Prerequisites

1. Docker Engine + Compose plugin on the host
2. [DuckDNS](https://www.duckdns.org/) subdomain pointed at your public IP
3. Router: **WAN TCP 9111 → host:9111** (or the port you set in `.env`)
4. Host firewall allows inbound TCP on that port (if enabled)

Port **80 is not required** (ACME uses DuckDNS DNS-01).

## Deploy

```bash
mkdir meter_buddy && cd meter_buddy
# Copy docker-compose.yml and .env.example from this deploy/ folder (or raw GitHub).
cp .env.example .env
# Edit .env: METER_BUDDY_DOMAIN, DUCKDNS_TOKEN, strong METER_BUDDY_AUTH_PASSWORD
docker compose up -d
```

Prefer pinning image tags in `docker-compose.yml` to a release (e.g. `:v0.5.0`) instead of `:latest`.

### Verify

```bash
# Liveness (no auth)
curl -fsS "https://${METER_BUDDY_DOMAIN}:${METER_BUDDY_HTTPS_PORT:-9111}/healthz"
# expect: {"ok":true}

# UI challenges Basic Auth
curl -o /dev/null -w "%{http_code}\n" "https://${METER_BUDDY_DOMAIN}:${METER_BUDDY_HTTPS_PORT:-9111}/"
# expect: 401
```

- UI: `https://<domain>:9111/`
- Upload: `https://<domain>:9111/api/meter-buddy/upload`

First boot may take a minute while Caddy obtains the certificate.

## Configuration

| Variable | Required | Notes |
| --- | --- | --- |
| `METER_BUDDY_DOMAIN` | Yes | DuckDNS hostname |
| `DUCKDNS_TOKEN` | Yes | DuckDNS API token |
| `METER_BUDDY_HTTPS_PORT` | No | Default `9111` |
| `METER_BUDDY_AUTH_USER` | Yes | Default `meter-buddy` |
| `METER_BUDDY_AUTH_PASSWORD` | Yes | Strong secret; not empty or `change-me` |
| `METER_BUDDY_DB_PATH` | Docker | `/data/meter_buddy.sqlite3` |

Do **not** set `METER_BUDDY_ALLOW_INSECURE_AUTH` in production. Never commit `.env`.

## Backup

- Download DB (Basic Auth): `GET /db`
- Or snapshot the Docker volume `*_backend_data`

Do **not** run `docker compose down -v` unless you intend to wipe the database.

## Upgrade

```bash
docker compose pull
docker compose up -d
```

## Source builds (maintainers)

To build images from this repo instead of pulling GHCR, use [`backend/docker-compose.yml`](../backend/docker-compose.yml) (`docker compose up --build -d` from `backend/`).

HTTPS cutover checklist from an old HTTP `:8000` stack: [backend/MIGRATION_HTTPS.md](../backend/MIGRATION_HTTPS.md).
