# GitHub token for firmware OTA mirror

The backend mirrors [GitHub Releases](https://github.com/bakroistvan/meter_buddy/releases) (app images named `meter-buddy-fw-v*.bin`) onto the home server so devices can OTA over the same HTTPS host as uploads. Device firmware pins Let’s Encrypt ISRG roots and **cannot** download release assets from GitHub’s CDN directly.

`METER_BUDDY_GITHUB_TOKEN` is **optional** for the public `bakroistvan/meter_buddy` repo (unauthenticated API allows 60 requests/hour). A fine-grained PAT is **recommended**: it raises the quota (~5,000/hour) and avoids intermittent 403 rate-limit failures. A token is **required** if the repository is private.

Daily poll + startup sync + occasional manual sync stay well under the anonymous limit in normal use; the token is still best practice for a always-on home server.

## 1. Create a fine-grained personal access token

1. Sign in to GitHub as a user who can read the repo.
2. Open **Settings → Developer settings → Personal access tokens → Fine-grained tokens**.
3. Click **Generate new token**.
4. Fill in:
   - **Token name:** e.g. `meter-buddy-firmware-mirror`
   - **Expiration:** pick a date you will remember to rotate (e.g. 90 days)
   - **Resource owner:** the repo owner (`bakroistvan` for the default public repo)
   - **Repository access:** **Only select repositories** → `meter_buddy`
5. Under **Repository permissions**:
   - **Contents:** **Read-only** (needed to download release assets)
   - **Metadata:** Read-only (granted automatically)
   - Do **not** grant Contents write, Administration, or any other write scopes
6. Generate the token and copy it once. Store it only in the server `.env` (never in git).

Classic PATs with `public_repo` / `repo` also work, but fine-grained tokens with a single-repo Contents read are preferred.

## 2. Install on the backend host

On the machine that runs Docker Compose:

```bash
cd backend
# Edit .env (create from .env.example if needed)
```

Add or uncomment:

```env
METER_BUDDY_GITHUB_TOKEN=github_pat_...
METER_BUDDY_GITHUB_REPO=bakroistvan/meter_buddy
METER_BUDDY_FIRMWARE_DIR=/data/firmware
METER_BUDDY_FIRMWARE_SYNC_INTERVAL_SEC=86400
```

Never commit `.env`. Restart so Compose injects the new variable into the `backend` service:

```bash
docker compose up -d
# or, if already running:
docker compose up -d --force-recreate backend
```

## 3. Verify

Replace host, user, and password with your values:

```bash
# Force a sync now (do not wait for the daily poll)
curl -i -u 'meter-buddy:your-strong-secret' \
  -X POST \
  https://changeme.duckdns.org:9111/api/meter-buddy/firmware/sync

# List mirrored tags / md5 / last sync status
curl -s -u 'meter-buddy:your-strong-secret' \
  https://changeme.duckdns.org:9111/api/meter-buddy/firmware | jq .
```

Success: HTTP 200 from sync; `releases` includes tags such as `v0.4.0` with a non-empty `md5`.

Failure hints:

| Symptom | Likely cause |
| --- | --- |
| Sync HTTP 502; `last_error` mentions `403` / rate limit | Missing or invalid token; add/rotate `METER_BUDDY_GITHUB_TOKEN` |
| Sync HTTP 502; `401` from GitHub | Token expired or revoked |
| Sync OK but empty `releases` | Release assets not named `meter-buddy-fw-v*.bin`, or only drafts/prereleases |
| Device OTA fails after sync | Firmware `FirmwareVersionUrl` / Basic Auth / TLS — see [docs/api/firmware.md](../docs/api/firmware.md) |

## 4. Rotate or revoke

1. Generate a new fine-grained token (same scopes).
2. Replace `METER_BUDDY_GITHUB_TOKEN` in `.env`.
3. Recreate the `backend` container as above.
4. Revoke the old token in GitHub Developer settings.

## Related

- Firmware OTA HTTP contract: [docs/api/firmware.md](../docs/api/firmware.md)
- Backend setup: [README.md](README.md)
- Example env keys: [.env.example](.env.example)
