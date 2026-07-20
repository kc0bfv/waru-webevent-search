#!/usr/bin/env bash
# cron_script.sh - Intended to be run by cron, updates events and commits changes to repo

cd /home/finity/Code/waru-webevent-search && nix-shell -p hugo --command ./local_test.sh && git add site data && git commit -m "Update content" && git push
