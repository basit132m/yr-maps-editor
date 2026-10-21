# Deploying to the Hostinger VPS

Step by step, from a fresh KVM 2 to `https://yrmapseditor.site` serving
traffic with a valid certificate.

Every command runs in the VPS terminal — either the **Browser terminal** in
hPanel (*VPS → Manage → Browser terminal*) or over SSH from your own machine.

Work through the steps in order. Each one ends with a check, so you always
know whether to carry on.

---

## Step 1 — Point the domain at the server

Do this first. The certificate in step 8 cannot be issued until DNS resolves,
and DNS changes take time to spread.

Find your VPS IP in hPanel under *VPS → Manage* (shown as **IP address**).

At whoever you bought `yrmapseditor.site` from, open the DNS editor and
create two records:

| Type | Name | Points to | TTL |
|---|---|---|---|
| A | `@` | your VPS IP | 300 |
| A | `www` | your VPS IP | 300 |

If records for `@` or `www` already exist, edit them instead of adding more —
two A records for the same name will send visitors to the wrong place.

**Check** (run on your own computer, or on the VPS after step 3):

```bash
dig +short yrmapseditor.site
```

It must print your VPS IP. If it prints nothing, wait and try again —
usually minutes, occasionally a few hours. Do not continue until it matches.

---

## Step 2 — Connect to the server

From your own machine:

```bash
ssh root@YOUR_VPS_IP
```

Use the root password from hPanel. Or just open the Browser terminal in
hPanel, which logs you in as root already.

**Check:** the prompt ends in `#`.

---

## Step 3 — Update the system

```bash
apt update && apt upgrade -y
```

If it asks about keeping a configuration file, keep the current one.

**Check:**

```bash
lsb_release -d
```

Ubuntu 22.04 or 24.04 is expected. Everything below assumes Ubuntu.

---

## Step 4 — Create a non-root user

Running a public service as root means one mistake costs you the whole box.

```bash
adduser --gecos "" yrme
usermod -aG sudo yrme
```

Set a strong password when prompted.

If you use an SSH key (recommended), copy it across now:

```bash
mkdir -p /home/yrme/.ssh
cp /root/.ssh/authorized_keys /home/yrme/.ssh/ 2>/dev/null || true
chown -R yrme:yrme /home/yrme/.ssh
chmod 700 /home/yrme/.ssh
```

**Check:** open a second terminal and confirm `ssh yrme@YOUR_VPS_IP` works
**before** you close the root session. Never lock yourself out.

---

## Step 5 — Open the firewall

```bash
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
```

Hostinger also has its own firewall in hPanel (*VPS → Manage → Firewall*).
If you have a rule set active there, allow TCP 80 and 443 in it too, or the
site stays unreachable no matter what `ufw` says.

**Check:**

```bash
ufw status
```

`22/tcp`, `80/tcp` and `443/tcp` should all show `ALLOW`.

---

## Step 6 — Install Docker

```bash
curl -fsSL https://get.docker.com | sh
usermod -aG docker yrme
```

**Check:**

```bash
docker --version && docker compose version
```

Both must print a version. If `docker compose` is missing, install the
plugin: `apt install -y docker-compose-plugin`.

---

## Step 7 — Get the code onto the server

Switch to the non-root user first:

```bash
su - yrme
```

Then clone:

```bash
git clone https://github.com/basit132m/yr-maps-editor.git
cd yr-maps-editor
git checkout claude/focused-cray-u11sxp
```

If the repository is private, GitHub will ask for a username and a personal
access token (your account password will not work).

**Check:**

```bash
ls
```

You should see `docker-compose.yml`, `Caddyfile`, `Dockerfile` and `app`.

---

## Step 8 — Configure and start

```bash
cp .env.example .env
nano .env
```

Set at least these two:

```
SITE_DOMAIN=yrmapseditor.site
ACME_EMAIL=your-real-email@example.com
```

Save with `Ctrl+O`, `Enter`, then exit with `Ctrl+X`.

> The email is only used by Let's Encrypt to warn you if a renewal is
> failing. Use an address you actually read.

Now build and start:

```bash
docker compose up -d --build
```

The first build takes a couple of minutes. Caddy then requests the
certificate automatically — there is no certbot step and nothing to renew
by hand.

**Check:**

```bash
docker compose ps
```

Both `app` and `caddy` should say `running`, and `app` should reach
`healthy` within about half a minute.

---

## Step 9 — Verify the site

On the server:

```bash
curl -sS http://127.0.0.1:80 -H "Host: yrmapseditor.site" -o /dev/null -w "%{http_code}\n"
```

`308` is correct — that is the redirect to HTTPS.

Then from any browser, open **https://yrmapseditor.site**. You should see
the upload page with a padlock.

Upload a real map and download the result. Open the downloaded file in a
text editor and confirm it has a `[ForcedOptions]` section at the end.

If the certificate did not arrive, check what Caddy is saying:

```bash
docker compose logs caddy | tail -30
```

Almost always it is DNS: go back to step 1 and confirm `dig +short
yrmapseditor.site` returns this server's IP.

---

## Step 10 — Test against your own maps

Synthetic tests only prove what we thought to check. Run the real thing:

```bash
mkdir -p ~/maps
# copy a few hundred real .map/.mpr/.yrm files into ~/maps, then:
docker compose exec app python3 tools/verify_corpus.py /maps -r
```

To make that work, add the folder to `docker-compose.yml` under the `app`
service:

```yaml
    volumes:
      - uploads:/var/lib/yrme
      - /home/yrme/maps:/maps:ro
```

then `docker compose up -d`.

It prints `N/N maps passed.` and exits non-zero if any map fails. Do this
before you announce the site.

---

## Running it day to day

**Deploy an update**

```bash
cd ~/yr-maps-editor
git pull
docker compose up -d --build
```

**Watch the logs**

```bash
docker compose logs -f app      # application
docker compose logs -f caddy    # certificates and requests
```

**Restart / stop**

```bash
docker compose restart
docker compose down             # stop everything
```

**Check disk** — uploads self-delete after 30 minutes, but logs grow:

```bash
df -h /
docker system prune -f          # reclaim old build layers
```

---

## If something breaks

| Symptom | Cause | Fix |
|---|---|---|
| Site unreachable, no certificate | DNS not pointing here yet | `dig +short yrmapseditor.site`, wait, retry |
| Browser warns about the certificate | Caddy could not complete the challenge | `docker compose logs caddy`; confirm ports 80 and 443 open in **both** ufw and hPanel |
| `502 Bad Gateway` | the app container is down | `docker compose ps`, then `docker compose logs app` |
| Upload fails on a big map | hitting the size cap | raise `max_size` in `Caddyfile` and `MAX_UPLOAD_BYTES` in `app/mapfile.py`, then rebuild |
| "Your upload has expired" | more than 30 minutes between the two steps | raise `YRME_UPLOAD_TTL` in `.env` |
| `permission denied` on docker | the group change has not applied | log out and back in, or run `newgrp docker` |
| Out of disk | old images and build layers | `docker system prune -a -f` |

---

## Hardening worth doing once the site is live

These are optional, in rough order of value:

1. **Disable SSH password login** (keys only). Edit `/etc/ssh/sshd_config`,
   set `PasswordAuthentication no`, then `systemctl restart ssh`. Make sure
   key login works first.
2. **Install fail2ban**: `apt install -y fail2ban`.
3. **Automatic security updates**:
   `apt install -y unattended-upgrades`.
4. **Back up `.env`** somewhere off the server. Nothing else on the box is
   irreplaceable — the code is in git and uploads are disposable.
5. **Rate limiting**, if the site gets busy or abused. Caddy's
   `rate_limit` directive, or put Cloudflare in front.
