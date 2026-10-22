#!/usr/bin/env bash
# Install PiPath on a Raspberry Pi, or update it to the latest version.
#
#   Double-click "Install-PiPath.desktop" (it downloads and runs this), or in a Terminal:
#   curl -fsSL https://raw.githubusercontent.com/jackallen28/BNTS_PIPath/main/tools/install_pipath.sh | bash
#
# What it does:
#   1. downloads the latest PiPath into ~/pipath (git if it's there, otherwise a zip)
#   2. adds PiPath to the menu (Programming) and the desktop, plus "Update PiPath" in the menu
#   3. opens PiPath
# Students' saved work lives in ~/PiPath/students and is never touched.
# Change PIPATH_DIR / PIPATH_BRANCH / PIPATH_REPO to install somewhere else or from another branch.
set -uo pipefail

REPO="${PIPATH_REPO:-jackallen28/BNTS_PIPath}"
BRANCH="${PIPATH_BRANCH:-main}"
DIR="${PIPATH_DIR:-$HOME/pipath}"
GIT_URL="https://github.com/$REPO.git"
ZIP_URL="https://github.com/$REPO/archive/refs/heads/$BRANCH.zip"
export GIT_TERMINAL_PROMPT=0          # never stop to ask for a GitHub login

say()  { printf '\n\033[1;36m%s\033[0m\n' "$*"; }
fail() {
  printf '\n\033[1;31m%s\033[0m\n' "$*"
  echo "Students' work in ~/PiPath has not been touched. Keep any backup branch, stash or previous installation shown above."
  exit 1
}

echo "============================================"
echo "   PiPath installer - BNTS Python tutor"
echo "============================================"

# ---------------------------------------------------------------- what this Pi has
python3 - <<'EOF' 2>/dev/null || fail "PiPath needs Python 3.11 or newer with Tkinter. Use Raspberry Pi OS Desktop (Bookworm or newer), or run: sudo apt install python3-tk"
import sys, tkinter
assert sys.version_info >= (3, 11)
EOF

fetch() {   # fetch URL FILE
  if command -v curl >/dev/null; then curl -fsSL --retry 2 -o "$2" "$1"
  elif command -v wget >/dev/null; then wget -q -O "$2" "$1"
  else python3 -c "import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])" "$1" "$2"
  fi
}

# ---------------------------------------------------------------- download
if [ -e "$DIR/.git" ] && command -v git >/dev/null; then
  say "Updating PiPath in $DIR ..."
  cd "$DIR" || fail "Can't open $DIR."
  source_url="$(git config --get remote.origin.url 2>/dev/null || true)"
  migrate=0
  case "$source_url" in
    "$GIT_URL"|"https://github.com/$REPO"|"git@github.com:$REPO.git"|"ssh://git@github.com/$REPO.git") ;;
    "https://github.com/jackallen28/jackallen.git"|"https://github.com/jackallen28/jackallen"|"git@github.com:jackallen28/jackallen.git")
      [ "$REPO" = "jackallen28/BNTS_PIPath" ] || fail "This folder uses a different repository. Set PIPATH_DIR to a new folder."
      migrate=1 ;;
    *) fail "This folder uses a different repository. Set PIPATH_DIR to a new folder." ;;
  esac
  # Fetch the requested source explicitly: the old origin has no main branch.
  git fetch --depth 1 "$GIT_URL" "$BRANCH" || fail "Couldn't download the update. Is this Pi on the internet?"
  backup="pipath-backup-$(date +%Y%m%d-%H%M%S)-$$"
  git branch "$backup" HEAD || fail "Couldn't preserve the current app version."
  echo "Previous app commits are preserved on branch: $backup"
  if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git ls-files --others --exclude-standard)" ]; then
    stash="before-update-$(date +%Y%m%d-%H%M%S)-$$"
    git stash push --include-untracked -q -m "$stash" || fail "Couldn't preserve your local app edits."
    echo "Local app edits and untracked files are preserved in git stash: $stash"
  fi
  git checkout -q -B "$BRANCH" FETCH_HEAD || fail "Couldn't switch to the new version. Your previous version and edits are backed up."
  if [ "$migrate" = "1" ]; then
    previous="pipath-previous-source-$(date +%Y%m%d-%H%M%S)-$$"
    git remote rename origin "$previous" || fail "Couldn't preserve the old remote."
    git remote add origin "$GIT_URL" || fail "Couldn't select the new repository."
    echo "Old repository settings retained as remote: $previous"
  fi
  git update-ref "refs/remotes/origin/$BRANCH" FETCH_HEAD || fail "Couldn't record the new release."
  git branch --set-upstream-to="origin/$BRANCH" "$BRANCH" >/dev/null || fail "Couldn't track the new release branch."
elif command -v git >/dev/null && [ ! -e "$DIR" ]; then
  say "Downloading PiPath into $DIR ..."
  git clone -q --depth 1 -b "$BRANCH" "$GIT_URL" "$DIR" || fail "Couldn't download PiPath. Is this Pi on the internet?"
else
  say "Downloading PiPath ..."
  tmp="$(mktemp -d)" || fail "Can't make a temporary folder."
  trap 'rm -rf "$tmp"' EXIT
  fetch "$ZIP_URL" "$tmp/pipath.zip" || fail "Couldn't download PiPath. Is this Pi on the internet?"
  python3 -m zipfile -e "$tmp/pipath.zip" "$tmp/x" || fail "The download was damaged. Try again."
  new="$(find "$tmp/x" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
  [ -f "$new/main.py" ] || fail "The download doesn't look like PiPath."
  if [ -e "$DIR" ]; then
    old="$DIR.old-$(date +%Y%m%d-%H%M%S)"
    mv "$DIR" "$old" || fail "Can't move the old version out of the way."
  fi
  mv "$new" "$DIR" || { [ -n "${old:-}" ] && mv "$old" "$DIR"; fail "Can't put the new version in $DIR."; }
  [ -n "${old:-}" ] && echo "Previous installation retained at $old."
fi

# Record managed ZIP installations so launch updates can detect and preserve local edits.
if [ ! -e "$DIR/.git" ]; then
  (cd "$DIR" && python3 - "$REPO" "$BRANCH" <<'PYMANIFEST'
import sys
from pathlib import Path
from pipath.updater import write_archive_manifest
write_archive_manifest(Path.cwd(),sys.argv[1],sys.argv[2])
PYMANIFEST
  ) || fail "Could not record the installation version."
fi

# ---------------------------------------------------------------- menu, desktop icon, quick start
cd "$DIR" || fail "Can't open $DIR."
chmod +x install.sh tools/install_pipath.sh 2>/dev/null
say "Adding PiPath to the menu and the desktop ..."
bash ./install.sh || fail "The menu and desktop icon couldn't be added."

version="$(git -C "$DIR" log -1 --format='%h, %cd' --date=short 2>/dev/null || date +%Y-%m-%d)"
say "Done! PiPath is installed ($version)."
echo "Open it from the desktop icon, or the menu: Programming > PiPath."
echo "PiPath checks for updates when opened on a Raspberry Pi. It also works offline."
echo "For a manual update: menu > Programming > Update PiPath (needs the internet)."

if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && [ -z "${PIPATH_NO_LAUNCH:-}" ]; then
  say "Opening PiPath ..."
  (cd "$DIR" && setsid python3 main.py >/dev/null 2>&1 &)
fi
exit 0
