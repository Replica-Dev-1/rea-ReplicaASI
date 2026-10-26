/* ca.js - the coin's address in the header (written into the page as data-ca), with a copy button. */
(function () {
  "use strict";
  const box = document.getElementById("ca");
  if (!box) return;
  const ca = box.dataset.ca, btn = box.querySelector("button"), addr = box.querySelector(".addr");
  btn.onclick = async () => {
    try { await navigator.clipboard.writeText(ca); }
    catch {                                             // older browsers: select it so the visitor can copy by hand
      addr.textContent = ca;
      const r = document.createRange(); r.selectNodeContents(addr);
      const s = getSelection(); s.removeAllRanges(); s.addRange(r);
    }
    btn.textContent = "copied"; setTimeout(() => { btn.textContent = "copy"; }, 1600);
  };
})();
