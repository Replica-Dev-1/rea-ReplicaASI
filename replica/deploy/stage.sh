#!/bin/sh
# deploy REPLICA to your server (run from the repo root: REPLICA_HOST=root@your-server sh deploy/stage.sh). Live at https://replicaasi.com (deploy/replicaasi.conf).
# Sandboxed (deploy/replica.service): own user, own /opt/replica + /var/lib/replica, socket /run/replica/app.sock for nginx,
# no localhost / private network, other projects' folders and .env files invisible. Env /etc/replica.env (root 600):
# RP_RPC (Robinhood Chain RPC, optional; config.json has the public one) and RP_PUBLIC. Tests run before the restart; nginx reloads only if its check passes.
set -e
# Resolve paths from the checkout, and fail before any server change if a release file is missing.
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
for file in \
  server/app.py server/chain.py server/replica_model.py server/skills.py server/runner.py server/hosted_rea.py server/faces.py server/lore.py server/rooms.json server/config.json \
  static/index.html static/paper.css static/page.js static/ca.js static/rea.js static/skills.js static/runner.js static/replica.js static/face.js static/bench.js static/wallets.js static/web3.iife.min.js \
  static/samples/search/index.html static/samples/search/search.js static/samples/search/child.js static/samples/search/demo.js \
  static/samples/search/fixtures.json static/samples/search/parent.skill.json static/samples/search/child.skill.json static/samples/search/preview.png \
  static/runner/index.html static/runner/replica-runner.zip static/runner/guide.txt tools/replica_runner.py tools/replica_agent.py tools/replica_package.py tools/unpack_skill.py tools/hosted_rea_worker.py agents/replica/agent.json \
  static/news/index.html tests/test_model.py tests/test_lineage.py tests/test_skills.py tests/test_runner.py tests/test_native_agent.py tests/test_native_flow.py tests/test_hosted_rea.py tests/parity.mjs \
  deploy/replica.service deploy/replica-rea.service deploy/hosted-rea.conf samples/notes-target/search.cjs samples/notes-target/LICENSE.txt deploy/replica-zones.conf deploy/replicaasi.conf
do
  if [ ! -r "$file" ]; then printf 'Missing required release file: %s\n' "$file" >&2; exit 1; fi
done
case "${1-}" in
  --check) printf '%s\n' 'Required release files present. No server changes made.'; exit 0 ;;
  '') ;;
  *) printf '%s\n' 'Usage: sh deploy/stage.sh [--check]' >&2; exit 2 ;;
esac
B="${REPLICA_HOST:?set REPLICA_HOST, e.g. REPLICA_HOST=root@your-server}"
# Hosted REA requires the separately installed, pinned offline worker runtime.
ssh -n $B 'test -x /opt/replica-rea-worker/node/bin/node && test -f /opt/replica-rea-worker/integrations/rea/node_modules/rea-agents/scripts/rea.mjs && id replica-rea >/dev/null && test -d /var/lib/replica-rea'
ssh -n $B 'mkdir -p /opt/replica/samples/notes-target /etc/systemd/system/replica-rea.service.d /etc/systemd/system/replica.service.d'
scp -q samples/notes-target/search.cjs samples/notes-target/LICENSE.txt $B:/opt/replica/samples/notes-target/
scp -q deploy/replica-rea.service $B:/etc/systemd/system/replica-rea.service
scp -q deploy/hosted-rea.conf $B:/etc/systemd/system/replica.service.d/hosted-rea.conf
ssh -n $B 'id replica >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin replica; mkdir -p /opt/replica/server /opt/replica/static /opt/replica/static/news /opt/replica/static/samples/search /opt/replica/static/runner /opt/replica/tools /opt/replica/tests /etc/systemd/system/replica.service.d'
scp -q server/app.py server/chain.py server/replica_model.py server/skills.py server/runner.py server/hosted_rea.py server/faces.py server/lore.py server/rooms.json server/config.json $B:/opt/replica/server/
scp -q static/index.html static/paper.css static/page.js static/ca.js static/rea.js static/skills.js static/runner.js static/replica.js static/face.js static/bench.js static/wallets.js static/web3.iife.min.js $B:/opt/replica/static/
scp -q static/samples/search/* $B:/opt/replica/static/samples/search/
scp -q static/runner/* $B:/opt/replica/static/runner/
scp -q tools/replica_runner.py tools/replica_agent.py tools/replica_package.py tools/unpack_skill.py tools/hosted_rea_worker.py $B:/opt/replica/tools/
ssh -n $B 'mkdir -p /opt/replica/agents/replica'
scp -q agents/replica/agent.json $B:/opt/replica/agents/replica/
scp -q static/news/index.html $B:/opt/replica/static/news/index.html
scp -q tests/test_model.py tests/test_lineage.py tests/test_skills.py tests/test_runner.py tests/test_native_agent.py tests/test_native_flow.py tests/test_hosted_rea.py tests/parity.mjs $B:/opt/replica/tests/
ssh -n $B "cp /etc/systemd/system/replica.service /root/replica.service.prev 2>/dev/null; true"
scp -q deploy/replica.service $B:/etc/systemd/system/replica.service
scp -q deploy/replica-zones.conf $B:/etc/nginx/conf.d/replica-zones.conf
scp -q deploy/replicaasi.conf $B:/etc/nginx/conf.d/replicaasi.conf.new
ssh -n $B "set -e
  test -x /opt/replica/venv/bin/python || python3 -m venv /opt/replica/venv
  /opt/replica/venv/bin/python -c 'import numpy, cryptography' 2>/dev/null || /opt/replica/venv/bin/pip install -q numpy cryptography
  sed -i '/^RP_RPC_SEED=/d; /^RP_RPC_GATE=/d' /etc/replica.env
  rm -f /opt/replica/static/deploy-contract.html /opt/replica/static/deploy-contract.js /opt/replica/static/Replica.json
  chown -R root:root /opt/replica; chmod -R a+rX /opt/replica
  cd /opt/replica; if ! { venv/bin/python tests/test_model.py > /tmp/rp_t1.log && venv/bin/python tests/test_lineage.py > /tmp/rp_t2.log && venv/bin/python tests/test_skills.py > /tmp/rp_t3.log && venv/bin/python tests/test_runner.py > /tmp/rp_t4.log && venv/bin/python tests/test_native_agent.py > /tmp/rp_t5.log; }; then grep -h FAIL /tmp/rp_t1.log /tmp/rp_t2.log /tmp/rp_t3.log /tmp/rp_t4.log /tmp/rp_t5.log || true; tail -qn4 /tmp/rp_t1.log /tmp/rp_t2.log /tmp/rp_t3.log /tmp/rp_t4.log /tmp/rp_t5.log; echo TESTS_FAILED_NOT_DEPLOYED; exit 1; fi; tail -qn1 /tmp/rp_t1.log /tmp/rp_t2.log /tmp/rp_t3.log /tmp/rp_t4.log /tmp/rp_t5.log
  rm -rf server/__pycache__ tests/__pycache__
  # hide every other .env file in /etc from the service (regenerated each deploy)
  { echo '[Service]'; for f in /etc/*.env; do [ \"\$f\" = /etc/replica.env ] || echo \"InaccessiblePaths=-\$f\"; done; } > /etc/systemd/system/replica.service.d/hide-env.conf
  { echo '[Service]'; for f in /etc/*.env; do echo \"InaccessiblePaths=-\$f\"; done; } > /etc/systemd/system/replica-rea.service.d/hide-env.conf
  systemctl daemon-reload && systemctl enable replica.service && systemctl restart replica.service && systemctl enable replica-rea.service && systemctl restart replica-rea.service
  sleep 2
  if ! curl -sf --unix-socket /run/replica/app.sock http://replica/api/health; then echo SERVICE_FAILED_ROLLING_BACK; journalctl -u replica -n 15 --no-pager; cp /root/replica.service.prev /etc/systemd/system/replica.service; rm -f /etc/systemd/system/replica.service.d/hide-env.conf; systemctl daemon-reload; systemctl restart replica; rm -f /etc/nginx/conf.d/replicaasi.conf.new; exit 1; fi; echo
  cp /etc/nginx/conf.d/replicaasi.conf /root/replicaasi.conf.prev 2>/dev/null || true; mv /etc/nginx/conf.d/replicaasi.conf.new /etc/nginx/conf.d/replicaasi.conf
  if nginx -t 2>/dev/null; then systemctl reload nginx; echo NGINX_RELOADED; else cp /root/replicaasi.conf.prev /etc/nginx/conf.d/replicaasi.conf; echo NGINX_CHECK_FAILED_RESTORED; nginx -t; fi"
