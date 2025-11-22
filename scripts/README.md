# gen_htpasswd.py — Minimal bcrypt htpasswd generator

Purpose
- Produce a single htpasswd-style line (`username:hash`) using bcrypt. Intended to create entries for `traefik-users.txt` used by Traefik basic auth.

Dependencies
- Python 3.8+ and the `bcrypt` package.
- Install with: ``pip install bcrypt``

Quick Usage
- Prompt for password and print the htpasswd line:
```
python scripts/gen_htpasswd.py admin
```
- Provide password on the command line (convenient when you already generated one):
```
python scripts/gen_htpasswd.py admin 'MyS3cureP@ss'
```

What it prints
- A single line suitable for `traefik-users.txt`, for example:
```
admin:$2b$12$...bcrypt-hash...
```

Security notes
- Do NOT commit `traefik-users.txt` to git. Treat it as sensitive credentials.
- The bcrypt hash is strong, but keep the underlying passwords secret and rotate them if you suspect a leak.

Updating `traefik-users.txt`
- Manually paste the printed line into `traefik-users.txt` on the server, or use the script output redirection:
```
python scripts/gen_htpasswd.py admin 'MyS3cureP@ss' > traefik-users.txt
```
- After updating the file on the server, restart Traefik to reload credentials:
```
docker compose -f docker-compose_server.yml restart traefik
```

Notes
- This script purposely avoids Docker, passlib or complex features — it's a tiny helper that requires only `bcrypt`.
