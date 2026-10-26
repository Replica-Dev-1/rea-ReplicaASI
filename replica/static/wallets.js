/* wallets.js - find every Solana wallet the visitor has installed (Phantom, Solflare, Backpack, ...) through the
   Wallet Standard, and wrap the chosen one in the small shape page.js uses:
     { name, connect() -> address, signMessage(text) -> base64 signature, mintAsset(createIx(owner), extraSigner) -> signature }
   The wallet does all signing; this file never sees the wallet's key. Chain calls go through the site's narrow relay
   (api/rpc: blockhash, send, status). Falls back to window.phantom.solana if no standard wallet registers. */
(function (root) {
  "use strict";
  const W3 = root.solanaWeb3;
  const found = [];
  const ok = (w) => w && Array.isArray(w.chains) && w.chains.some((c) => String(c).startsWith("solana:")) &&
    w.features && w.features["standard:connect"] && w.features["solana:signTransaction"] && w.features["solana:signMessage"];
  const register = (...ws) => { for (const w of ws) if (ok(w) && !found.includes(w)) found.push(w); return () => {}; };
  const api = { register };
  root.addEventListener("wallet-standard:register-wallet", (e) => { try { e.detail(api); } catch { /* bad wallet */ } });
  try { root.dispatchEvent(new CustomEvent("wallet-standard:app-ready", { detail: api })); } catch { /* old browser */ }

  const b64 = (u8) => btoa(String.fromCharCode(...u8));
  const conn = () => new W3.Connection(new URL("api/rpc", location.href).href, { commitment: "confirmed", disableRetryOnRateLimit: true });

  // the way Phantom asks for it (docs.phantom.com, domain and transaction warnings): explicit compute limit, simulated
  // before signing (sigVerify off), the WALLET signs first, our extra signer after, then sent through our RPC with preflight
  async function sendWith(signTx, payer, ix, extraSigner) {
    const c = conn();
    const { blockhash, lastValidBlockHeight } = await c.getLatestBlockhash();
    const build = (units) => {
      const tx = new W3.Transaction().add(W3.ComputeBudgetProgram.setComputeUnitLimit({ units }), ix);
      tx.recentBlockhash = blockhash; tx.feePayer = payer;
      return tx;
    };
    const sim = await c.simulateTransaction(new W3.VersionedTransaction(build(200000).compileMessage()), { sigVerify: false, commitment: "confirmed" });
    if (sim.value.err) throw new Error("the mint would fail on chain (" + JSON.stringify(sim.value.err) + "); nothing was sent");
    const tx = build(Math.ceil((sim.value.unitsConsumed || 60000) * 1.3) + 2000);
    const signed = await signTx(tx);
    if (extraSigner) signed.partialSign(extraSigner);
    const sig = await c.sendRawTransaction(signed.serialize(), { maxRetries: 5 });
    for (let i = 0; i < 45; i++) {               // ~90 s
      await new Promise((r) => setTimeout(r, 2000));
      const st = (await c.getSignatureStatuses([sig])).value[0];
      if (st && st.err) throw new Error("the transaction failed on chain");
      if (st && (st.confirmationStatus === "confirmed" || st.confirmationStatus === "finalized")) return sig;
      if (i % 5 === 4 && (await c.getBlockHeight()) > lastValidBlockHeight) throw new Error("the transaction expired before it landed; try again");
    }
    throw new Error("still not confirmed; check your wallet before trying again");
  }

  function wrapStandard(w) {
    let account = null, pk = null;
    const signTx = async (tx) => {
      const raw = tx.serialize({ requireAllSignatures: false, verifySignatures: false });
      const [out] = await w.features["solana:signTransaction"].signTransaction({ account, transaction: raw, chain: "solana:mainnet" });
      return W3.Transaction.from(out.signedTransaction);
    };
    return {
      name: w.name,
      async connect() {
        const r = await w.features["standard:connect"].connect();
        account = (r.accounts || w.accounts || [])[0];
        if (!account) throw new Error("the wallet didn't share an account");
        pk = new W3.PublicKey(account.publicKey || account.address);
        return pk.toBase58();
      },
      async signMessage(text) {
        const [out] = await w.features["solana:signMessage"].signMessage({ account, message: new TextEncoder().encode(text) });
        return b64(out.signature);
      },
      mintAsset: (makeIx, extraSigner) => sendWith(signTx, pk, makeIx(pk), extraSigner),
    };
  }

  function wrapLegacy(p, name) {
    return {
      name,
      async connect() { const r = await p.connect(); return (r.publicKey || p.publicKey).toBase58(); },
      async signMessage(text) { const r = await p.signMessage(new TextEncoder().encode(text), "utf8"); return b64(r.signature || r); },
      mintAsset: (makeIx, extraSigner) => sendWith((tx) => p.signTransaction(tx), p.publicKey, makeIx(p.publicKey), extraSigner),
    };
  }

  function list() {
    const out = found.map(wrapStandard);
    const legacy = (root.phantom && root.phantom.solana) || root.solana;
    if (legacy && !out.some((w) => /phantom/i.test(w.name))) out.push(wrapLegacy(legacy, "Phantom"));
    return out;
  }
  root.Wallets = { list };
})(window);
