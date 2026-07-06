# Windows Git-Bash Pitfalls

Common issues when using `git` from **git-bash (MSYS2)** on Windows — especially from Chinese VPS with slow connections to GitHub.

## 1. Stale `index.lock` Blocking Commands

When a `git` process is killed mid-operation (e.g. Ctrl+C, timeout, force-killed), `index.lock` persists and blocks ALL subsequent git commands.

**Symptoms:**
```
fatal: Unable to create '.../.git/index.lock': File exists.
Another git process seems to be running in this repository, or the
lock file may be stale.
```

**Fix — find and kill the zombie git process:**
```bash
# Find the git process holding the lock
ps aux | grep -i git

# Kill it
kill -9 <PID>

# Then verify lock is gone
rm -f .git/index.lock
git status
```

**If `rm` fails with "Device or resource busy":**
```bash
# Use Windows cmd to bypass MSYS handle issue
cmd //c "del /f /q C:\path\to\.git\index.lock"

# Or use Python to remove the entire .git directory
python -c "import shutil,os; shutil.rmtree('.git', onerror=lambda fn,p,e: None)"
```

**If .git directory can't be fully removed, reinit in place:**
```bash
# Try cmd rmdir
cmd //c "rmdir /s /q C:\path\to\.git"

# If it partially succeeds (some files skipped), just reinit:
git init
git branch -m main
```

## 2. Git Init in Clean Working Directory

After a stuck .git directory is cleaned, always start fresh:

```bash
rm -rf .git 2>/dev/null
git init
git branch -m main
git config user.email "user@example.com"
git config user.name "username"
```

## 3. `.gitignore` for Trading / ML Projects

Patterns that commonly cause large initial repo bloat:

```gitignore
# Must exclude
node/                     # Node.js binaries (can be 147MB!)
logs/                     # Session logs, trade logs (thousands of JSON files)
sessions/                 # Hermes session DB
output/                   # Cron output artifacts
audio_cache/              # Generated audio files
cache/                    # Hermes internal cache

# Binaries
bin/
*.exe

# Lock & auth
*.lock
auth.json
.env

# Backups
*.bak*

# Curator backups (large tar.gz archives)
skills/.curator_backups/
```

## 4. Large Initial Commit — Fixing Over-Inclusion

If you accidentally commit too much (e.g. `node/`, `logs/`):

```bash
# 1. Update .gitignore with the missing patterns
# 2. Remove tracked files from index without deleting from disk
git rm -r --cached node/
git rm -r --cached logs/

# 3. Amend the commit (no new commit needed)
git commit --amend -m "Same commit message"

# 4. Verify size
git count-objects -v | grep size-pack
```

## 5. Force Push After Amending Initial Commit

If you amended the initial commit, the remote history diverges:

```bash
git push -u origin main --force
```

## 6. LF/CRLF Warnings

On Windows git-bash, LF→CRLF warnings are cosmetic and safe to ignore:
```
warning: in the working copy of 'file.py', LF will be replaced by CRLF
```

To suppress: add `.gitattributes` with `* text=auto`.

## 7. MSYS Process Management

On MSYS git-bash, `git` spawns a subprocess that persists. Two PIDs per git command is normal. After a timeout, the process may linger:
```bash
# Check for zombie git
ps aux | grep -i git

# Mass kill
kill -9 $(ps aux | grep -i git | awk '{print $1}') 2>/dev/null
```

## 8. HTTPS Push Times Out — Switch to SSH

From Chinese VPS (Tencent, Alibaba, etc.), `git push` over **HTTPS often times out** (even with `http.postBuffer=524288000` and 300s timeout). The TCP connection succeeds but the data transfer stalls.

**Fix — always set up SSH for repos on Chinese VPS:**

```bash
# 1. Generate key
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N "" -C "your@email.com"

# 2. Tell user to add public key to github.com/settings/keys
cat ~/.ssh/id_ed25519.pub

# 3. Test connection
ssh -o StrictHostKeyChecking=no -i ~/.ssh/id_ed25519 -T git@github.com
# Expected: "Hi username! You've successfully authenticated"

# 4. Switch remote from HTTPS to SSH
git remote set-url origin git@github.com:owner/repo.git

# 5. Push (use background mode with generous timeout)
git push -u origin main
```

**SSH works better because:**
- Persistent TCP (less sensitive to latency spikes than HTTPS)
- No token validation per request
- No credential helper conflicts (the `helper-selector` on Windows git-bash can override URL-embedded credentials)

**Troubleshooting SSH push timeout:**
If SSH auth succeeds but push still times out, the issue is data transfer speed. Use `background=true` + `notify_on_complete=true` with a 300-600s timeout:
```bash
terminal(command="git push -u origin main", background=true, notify_on_complete=true, timeout=600)
```

## 9. Token Scope Mismatch: `gh` CLI vs `curl` API

A GitHub token may **work for REST API calls** (curl) but **fail for `gh auth login` or `gh auth status`** due to missing `read:org` scope. This is confusing because the token clearly works (API returns user data and can create repos).

**Symptoms:**
```bash
# This works — creates repo, returns user data
curl -H "Authorization: token $TOKEN" https://api.github.com/user/repos -d '{"name":"test"}'
# → 200 OK

# This fails — missing read:org
echo "$TOKEN" | gh auth login --with-token
# → "error validating token: missing required scope 'read:org'"

gh auth status
# → "The token in GITHUB_TOKEN is invalid"
```

**Workaround — don't use `gh`, use `curl` directly:**
```bash
# Create repo via API
curl -s -X POST -H "Authorization: token $TOKEN" \
  https://api.github.com/user/repos \
  -d '{"name":"repo-name","private":true}'

# Then set remote and push via SSH (see section 8)
git remote add origin git@github.com:owner/repo-name.git
```

**Alternatively, generate a token WITH `read:org` scope** from github.com/settings/tokens — this lets `gh` work normally.

The important lesson: **"token invalid" from `gh` does NOT mean the token is broken** — it means the token lacks `read:org`. The token's `repo` scope is sufficient for curl API calls and git HTTPS/SSH pushes.

## 10. Installing `gh` CLI on Windows Without Admin

When `gh` is not installed and you have no admin rights:

```bash
# Download the portable zip
curl -L -o gh.zip "https://github.com/cli/cli/releases/download/v2.63.2/gh_2.63.2_windows_amd64.zip"
unzip -o gh.zip -d gh_extract

# Copy to a directory in PATH
mkdir -p ~/bin
cp gh_extract/bin/gh.exe ~/bin/

# Add to PATH (persistent via .bashrc)
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
export PATH="$HOME/bin:$PATH"

# Verify
gh --version
```

No admin, no installer, no winget needed.
