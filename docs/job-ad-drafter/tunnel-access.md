# Reaching the job-ad service from your machine

The service runs privately on the server (`127.0.0.1:4310`); it is not on the internet. You reach it through an SSH tunnel with a key that can do nothing else on the server.

## One-time setup (2 minutes)

1. Create an SSH key if you don't have one:
   ```bash
   ssh-keygen -t ed25519 -C "jobad-tunnel"
   ```
   Press Enter for the defaults. This creates `~/.ssh/id_ed25519` (private, keep it) and `~/.ssh/id_ed25519.pub` (public).
2. Send the contents of `~/.ssh/id_ed25519.pub` (one line starting `ssh-ed25519 …`) to Andile. It gets added to the server's `tunnel` account.

## Every time you want the service

```bash
ssh -N -L 4311:127.0.0.1:4310 tunnel@169.58.230.83
```

Leave that terminal open. While it runs, the service is at:

- **http://127.0.0.1:4311/docs** — interactive console (try the endpoints from the browser)
- **http://127.0.0.1:4311/healthz** — versions and today's spend
- Your code: base URL `http://127.0.0.1:4311`

Close the terminal (Ctrl+C) and the tunnel is gone. Nothing changes on the server.

Notes
- `-N` means "no shell"; the account has none, so you only ever see the tunnel. Password login is disabled; only your key works.
- If port 4311 is busy locally, pick another: `-L 4400:127.0.0.1:4310` → `http://127.0.0.1:4400`.
- In production your app calls `http://127.0.0.1:4310` directly on the server; the tunnel is for development and testing only.
- Drafts cost real money (about 9 cents each) and there is a daily cap; `/v1/briefs/check` and `/v1/scores` with `"judge": false` are free.
- Contract and payloads: see the contract page Andile shared, or `/docs` through the tunnel.
