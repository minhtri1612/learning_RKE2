#!/usr/bin/env bash
set -e
ENTRY="13.237.3.9\tmeo-stationery-dev.local"
sudo sed -i.bak -E '/meo-stationery-dev\.local/d' /etc/hosts
echo "$ENTRY" | sudo tee -a /etc/hosts
echo "Done: meo-stationery-dev.local"
