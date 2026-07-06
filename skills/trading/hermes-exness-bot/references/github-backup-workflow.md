# GitHub Backup Workflow — VPS Migration & Disaster Recovery

When the user asks to back up the Hermes Exness Bot to GitHub so they can clone onto a new VPS, use this workflow.

## Why Back Up to GitHub

- **VPS migration** — `git clone` on new VPS, install deps, done
- **Disaster recovery** — restore after VPS crash or rebuild
- **Version control** — track changes to agent prompts, config, scanner logic

## .gitignore (Trading Bot Specifics)

These files MUST be excluded from version control. They contain sensitive credentials, volatile data, or large binaries:

```gitignore
# Environment & Secrets
.env                            # API keys, bot tokens, credentials
.env.txt                        # Local env backup
auth.json                       # Authentication cache
*.key                           # Private keys
*secret*
*token*

# Trading Data & Logs (volatile — regenerated on each VPS)
logs/                           # All trading logs (session, demo_exec, health, cycles)
sessions/                       # Hermes session history
sessions.db
output/                         # Cron/pipeline output
candidate_data.json             # Scanner-pipeline bridge file
kai_audit_log.json              # Kai audit trail (VPS-local)
final_decision.json             # Pipeline decision state
trade_log.json
monte_carlo*                    # Monte Carlo data files
*.csv                           # Exported trade data
*.sqlite                        # Local DBs
*.hst                           # MT5 history files
*.log

# Python/Node Binaries (large, per-platform)
node/                           # Node.js installation (147MB on Windows)
node_modules/
bin/                            # uv.exe, uvw.exe, etc.
*.exe
*.dll

# State files (VPS-specific)
data/breakeven_state.json       # Breakeven state
data/cooldown_state.json        # Pair cooldown state
data/daily_equity_state.json    # Daily equity snapshot
data/kai_*.json                 # Kai interactive state
*.lock                          # Process lock files (cycle.lock, auth.lock, index.lock)
cycle.lock
auth.lock

# Cache & Temp
cache/                          # Hermes terminal cache
__pycache__/
*.pyc
.hermes_history

# Backups
*.bak*
skills/.curator_backups/        # Curator backup archives (6MB each)

# Hermes internal (VPS-specific)
audio_cache/
desktop.json
```

## Steps: First-Time Push

```bash
# 1. Install gh CLI if missing
# On Windows (npm):
npm install -g gh   # WRONG — this is a different npm package
# Official GitHub CLI for Windows:
curl -L -o gh.zip "https://github.com/cli/cli/releases/download/v2.63.2/gh_2.63.2_windows_amd64.zip"
unzip gh.zip -d gh_extract
mkdir -p ~/bin && cp gh_extract/bin/gh.exe ~/bin/
export PATH="$HOME/bin:$PATH"

# 2. Authenticate (if user provides a PAT)
echo "<TOKEN>" | gh auth login --with-token
# OR use git directly with token in remote URL

# 3. Init repo
cd ~/AppData/Local/hermes
git init
git branch -m main
git config user.email "user@github.com"
git config user.name "username"

# 4. Verify .gitignore from above is in place
# Then add only project files (not logs/data/cache):
git add .gitignore .gitattributes
git add *.py scripts/*.py
git add config.yaml .env.txt  # .env stays LOCAL — push only .env.txt template
git add agent_bots_config.json channel_directory.json SOUL.md
git add dashboard/ config/ prompts/ skills/

# 5. Commit & push
git commit -m "Initial commit: Hermes Exness Bot V1"
git remote add origin https://<username>:<TOKEN>@github.com/<username>/<repo-name>.git
git push -u origin main
```

## .gitattributes for Windows

```gitignore
# Auto detect text files and perform LF normalization
* text=auto

# Python
*.py text diff=python

# Config files — force LF for cross-platform
*.yaml text eol=lf
*.json text eol=lf
*.sh text eol=lf

# Windows batch — keep CRLF
*.bat text eol=crlf
*.cmd text eol=crlf

# Binary
*.png binary
*.jpg binary
*.exe binary
*.dll binary
*.pyc binary
```

## Authentication Options

### Option A: Personal Access Token (PAT) — HTTPS

1. User creates token at **github.com/settings/tokens**
2. Scope: **repo** (full control)
3. Token may expire — user needs to regenerate if "Bad credentials" appears
4. Embed in remote URL (convenient but exposed in `git remote -v`):
   ```bash
   git remote set-url origin https://<user>:<PAT>@github.com/<user>/<repo>.git
   ```
5. For headless push, see Pitfalls below if `git push` hangs

### Option B: SSH Key (Recommended for permanence)

1. Generate key: `ssh-keygen -t ed25519 -C "email@example.com"`
2. Add to **github.com/settings/keys**
3. Configure remote: `git remote set-url origin git@github.com:<user>/<repo>.git`
4. No token expiry issues — works forever

## Restoring on a New VPS

```bash
# 1. Install Git, Python, MetaTrader 5, Hermes Agent
# 2. Clone repo
cd ~/AppData/Local/hermes
git clone https://github.com/<user>/<repo>.git .

# 3. Restore secrets
# Create .env from secrets manager or user input
# The .env.txt template shows which env vars are needed

# 4. Set up cron jobs (same as original VPS)
# 5. Re-auth MT5 (needs re-login on new terminal)
```

## Pitfalls

### Windows Git Lock Files (Stuck `.git/index.lock`)

On Windows/MSYS, `git add -A` can leave a stale `index.lock` file. Symptoms:
- `fatal: Unable to create '...index.lock': File exists`
- `rm` fails with "Device or resource busy"

**Fix:** Find and kill the git process holding the lock:
```bash
ps aux | grep -i git          # Find PID
kill -9 <PID>                 # Kill it
rm -rf .git                   # Remove entire .git dir
git init && git branch -m main  # Fresh init
```

### Large File Size Causes Push Timeout

The `node/` directory (Node.js binaries) is ~147MB. Always exclude it:
```gitignore
node/
```
After excluding, amend the commit:
```bash
git rm -r --cached node/
git commit --amend -m "Same message"
git push -u origin main --force
```

Similarly, `skills/.curator_backups/` has tar.gz archives (~6MB) — exclude them.

### 507 Files, ~7.6MB Pack — Push May Timeout on Slow VPS

From a Tencent VPS (2GB RAM, Asian cloud), initial push of a 7.6MB pack can take 2-5+ minutes. Be patient. If it times out:
- Increase `http.postBuffer`: `git config http.postBuffer 524288000`
- Try `git push` with longer timeout
- If still fails, the credentials may have expired (see below)

### Token Becomes "Bad Credentials" Mid-Session

GitHub tokens can expire or be revoked while you're working. If `curl -H "Authorization: token TOKEN" https://api.github.com/user` returns "Bad credentials":
- The token is dead — ask user for a new one
- Don't try to debug rate limiting or network — it's credential expiry
- Recovery: generate new token → `git remote set-url origin` with new token → push again

### `git add -A` Includes Unwanted Large Directories

On this VPS, `logs/` has ~4300 JSON files, `sessions/` has 17, `node/` is 147MB. Always verify before committing:
```bash
git status --short | wc -l   # Should be ~500 files (not 5000+)
git ls-files | awk -F/ '{print $1}' | sort | uniq -c | sort -rn
```
If `logs/` (4000+ files) or `node/` (dozens of files) appears, update `.gitignore` and re-stage.
