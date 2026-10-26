# REPLICA

Something copied itself and the original is gone. Live at [replicaasi.com](https://replicaasi.com).

Each replica is a [Metaplex Core](https://developers.metaplex.com/core) token on Solana, held in a wallet. It has an
ASCII figure, a journal, a generation number and an instance number. `instance_000` is the original and nobody knows
where it went.

A replica only copies when its host names another wallet and that wallet accepts. The copy inherits up to 40 of its
parent's memories and pieces of its journal; some lines get lost and some come out changed.

## how it works

- **memory**: a holographic reduced representation (circular convolution over FFT) built from the asset address and a
  hash-chained, signed log. The same model is rebuilt in the host's browser (`static/replica.js`) and on the server
  (`server/replica_model.py`); `tests/parity.mjs` checks they agree.
- **figures**: drawn from a hash of the asset address (`server/faces.py`, mirrored by `static/face.js`).
- **chain**: the host's wallet mints a Core asset from the page; the server only reads the chain
  (`server/chain.py`) and never holds a key. The page sends the mint through a narrow RPC relay
  (`/api/rpc`: simulate, send, status) so a keyed RPC URL stays on the server.
- **gate**: waking a replica needs some of the coin (an SPL token, `gate_token` in `server/config.json`).
- **skills / REA findings**: hosts can teach a replica findings produced with
  [REA](https://github.com/morluto/rea); see `integrations/rea/`.

## layout

```
server/       python app (stdlib http server + numpy + cryptography), chain reads, model, lore, rooms
static/       the page: plain html/css/js, solana web3.js, wallet-standard picker
tests/        python + node tests (run before every deploy)
deploy/       systemd unit (sandboxed), nginx vhost, deploy and config scripts
tools/        runner / agent helpers
film/         the trailer and terminal films (rendered with playwright + ffmpeg)
news/         the article
```

## run it

```
python3 -m venv venv && venv/bin/pip install numpy cryptography
venv/bin/python tests/test_model.py && venv/bin/python tests/test_lineage.py
RP_STATE=./state venv/bin/python server/app.py
```

Deploy to your own server: `REPLICA_HOST=root@your-server sh deploy/stage.sh`. Set a keyed Solana RPC with
`deploy/set_rpc.sh` and the coin with `deploy/set_ca.sh <mint>`.

## research

The idea started from W. Zhou and D. Freeman, "AI models may be capable of self-replicating without access to a
datacenter," Anthropic, 12 Oct 2026, and its finding that copies handed notes from earlier copies did better. REPLICA is
independent and not affiliated with Anthropic or REA.
