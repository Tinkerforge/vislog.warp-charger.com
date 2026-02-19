#!/bin/sh
# Simple auto-deploy from github
# This is called on the vislog server with cron (as root).
# Git operations run as user vislog, service restart as root.
#
# Initial setup on the server (run once as user vislog):
#
#   cd /home/vislog
#   git clone --depth=1 --filter=blob:none --sparse \
#       git@github.com:Tinkerforge/warp-charger.git warp-charger
#   cd warp-charger
#   git sparse-checkout set api_doc_generator

set -e

BRANCH="master"
NEEDS_RESTART=0

# --- Update vislog.warp-charger.com ---
cd /home/vislog/vislog.warp-charger.com
su -s /bin/sh vislog -c "/usr/bin/git fetch origin $BRANCH"

LOCAL_HASH=$(su -s /bin/sh vislog -c "/usr/bin/git rev-parse HEAD")
REMOTE_HASH=$(su -s /bin/sh vislog -c "/usr/bin/git rev-parse origin/$BRANCH")

if [ "$LOCAL_HASH" != "$REMOTE_HASH" ]; then
    su -s /bin/sh vislog -c "/usr/bin/git reset --hard origin/$BRANCH"
    NEEDS_RESTART=1
fi

# --- Update warp-charger (sparse checkout, only api_doc_generator/) ---
cd /home/vislog/warp-charger
su -s /bin/sh vislog -c "/usr/bin/git fetch --depth=1 origin $BRANCH"

LOCAL_HASH=$(su -s /bin/sh vislog -c "/usr/bin/git rev-parse HEAD")
REMOTE_HASH=$(su -s /bin/sh vislog -c "/usr/bin/git rev-parse origin/$BRANCH")

if [ "$LOCAL_HASH" != "$REMOTE_HASH" ]; then
    su -s /bin/sh vislog -c "/usr/bin/git reset --hard origin/$BRANCH"
    NEEDS_RESTART=1
fi

# --- Restart service if either repo was updated ---
if [ "$NEEDS_RESTART" = "1" ]; then
    /usr/bin/systemctl restart vislog.warp-charger.com
fi
