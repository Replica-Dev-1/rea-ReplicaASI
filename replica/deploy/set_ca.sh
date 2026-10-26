#!/bin/sh
# set the coin (an SPL token on Solana, e.g. launched on pump.fun) that gates waking a replica. usage, from the repo root:
#   sh deploy/set_ca.sh <MINT_ADDRESS> [TICKER]
# checks on chain that the address is a token mint, reads the ticker from the chain if the RPC can (else give it),
# then sets gate_token and coin_ticker (the page shows $<ticker>).
set -e
CA="$1"; SYM="$2"
echo "$CA" | grep -Eq '^[1-9A-HJ-NP-Za-km-z]{32,44}$' || { echo "that is not a Solana address: $CA"; exit 1; }
OUT=$(ssh -n "${REPLICA_HOST:?set REPLICA_HOST, e.g. REPLICA_HOST=root@your-server}" "/opt/replica/venv/bin/python -c \"
import os, sys; sys.path.insert(0, '/opt/replica/server'); import chain as C
U = dict(l.strip().split('=', 1) for l in open('/etc/replica.env') if '=' in l).get('RP_RPC') or 'https://api.mainnet-beta.solana.com'
v = C.rpc(U, 'getAccountInfo', ['$CA', {'encoding': 'jsonParsed'}]).get('value') or {}
d = v.get('data') if isinstance(v.get('data'), dict) else {}
assert (d.get('parsed') or {}).get('type') == 'mint', 'not a token mint'
sym = ''
try: sym = C.rpc(U, 'getAsset', {'id': '$CA'})['content']['metadata']['symbol']
except Exception: pass
print('MINT', sym)\"") || { echo "that address is not a token mint on solana; nothing changed"; exit 1; }
[ -n "$SYM" ] || SYM=$(echo "$OUT" | sed -n 's/^MINT \(.*\)$/\1/p')
echo "$SYM" | grep -Eq '^[A-Za-z0-9]{1,16}$' || { echo "couldn't read the ticker from chain; run again with it: sh deploy/set_ca.sh $CA TICKER"; exit 1; }
echo "coin: \$$SYM at $CA"
sed -i "s#\"gate_token\": \"[^\"]*\"#\"gate_token\": \"$CA\"#; s#\"coin_ticker\": \"[^\"]*\"#\"coin_ticker\": \"$SYM\"#" server/config.json
ssh -n "${REPLICA_HOST:?set REPLICA_HOST, e.g. REPLICA_HOST=root@your-server}" "set -e
  sed -i 's#\"gate_token\": \"[^\"]*\"#\"gate_token\": \"$CA\"#; s#\"coin_ticker\": \"[^\"]*\"#\"coin_ticker\": \"$SYM\"#' /opt/replica/server/config.json
  systemctl restart replica; sleep 2
  curl -s --unix-socket /run/replica/app.sock http://replica/api/config | grep -o '\"coin_ticker\": \"[^\"]*\", \"gate_token\": \"[^\"]*\"'"
