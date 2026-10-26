#!/bin/sh
# give REPLICA its own Solana mainnet RPC (e.g. a Helius or QuickNode endpoint made just for REPLICA). usage, from the repo root:
#   sh deploy/set_rpc.sh "https://YOUR-ENDPOINT"
# The URL goes only into /etc/replica.env on the server (root 600), never the page. It is checked to be Solana mainnet first.
set -e
URL="$1"
case "$URL" in https://*) ;; *) echo "give the full https:// RPC url"; exit 1 ;; esac
ssh -n "${REPLICA_HOST:?set REPLICA_HOST, e.g. REPLICA_HOST=root@your-server}" "set -e
  c=\$(curl -s -m 10 -X POST -H 'Content-Type: application/json' -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"getGenesisHash\"}' '$URL' | grep -o 5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d || true)
  [ -n \"\$c\" ] || { echo 'that RPC did not answer as Solana mainnet; nothing changed'; exit 1; }
  cp /etc/replica.env /root/replica.env.before-rpc
  sed -i '/^RP_RPC=/d' /etc/replica.env; echo 'RP_RPC=$URL' >> /etc/replica.env
  systemctl restart replica; sleep 2
  curl -sf --unix-socket /run/replica/app.sock http://replica/api/health && echo ' replica restarted on its own RPC'"
