/* face.js - a REPLICA's identity from its token address alone: a tall boxy ASCII figure with its name stamped in the
   bottom bar. Mirror of faces.py, character for character (checked by tests/parity.mjs). */
(function (root) {
  "use strict";
  const EYES = "Oo0@QxX*.^-=qpdb";
  const EYELINE = ["  1   2  ", " 1    2  ", "  1  2   ", "   1   2 ", "  1    2 ", " 1   2   ", "  12     ", "   1  2  "];
  const CHEEKS = [[">", "<"], [")", "("], ["*", "*"], ["~", "~"], ["=", "="], [".", "."], ["o", "o"], ["'", "'"]];
  const NOSE = "^v.,~-xo";
  const BODY = [["  ___  ", "  |o|  ", "  | |  ", "  '-'  "], ["  /-\\  ", "  | |  ", "  | |  ", "  \\-/  "],
    ["  ___  ", "  |_|  ", "", "  ---  "], ["  ,_,  ", "  |||  ", "  |||  ", "  ```  "],
    ["  ===  ", "  [ ]  ", "  [ ]  ", "  ===  "], [" _____ ", " |   | ", " |___| ", ""],
    ["  ~~~  ", "  ) (  ", "  ( )  ", "  ~~~  "], ["   _   ", "  / \\  ", "  \\_/  ", "   v   "]];
  const NAMES = ["Repeat", "Echo", "Again", "Copy", "Mirror", "Twice", "Twin", "Loop", "Return", "Remain", "Rerun", "Recall",
    "Relay", "Redo", "Reprise", "Undo"];
  const TEMPER = ["curious", "guarded", "restless", "gentle", "cold", "playful", "watchful", "lost"];
  const HABIT = ["counts doors", "hums static", "repeats the last word", "keeps a list of exits", "asks who sent you",
    "remembers rooms that are not there", "answers a second late", "writes on the walls"];
  const W = 9;
  const subtle = (typeof crypto !== "undefined" && crypto.subtle) || require("crypto").webcrypto.subtle;
  const row = (inner) => "|" + inner.padEnd(W) + "|";

  async function identity(asset) {
    const b = new Uint8Array(await subtle.digest("SHA-256", new TextEncoder().encode(asset)));
    const [c1, c2] = CHEEKS[b[3] % 8];
    const eyes = EYELINE[b[8] % 8].replace("1", EYES[b[2] % 16]).replace("2", EYES[b[9] % 16]);
    const inners = ["", eyes, "  " + c1 + " " + NOSE[b[5] % 8] + " " + c2, "", ...BODY[b[4] % 8].map((x) => " " + x)];
    const face = inners.map(row);
    const name = NAMES[b[15] % 16];
    face.push("|" + "_".repeat(W - name.length) + name + "|");
    const hex = (x) => x.toString(16).toUpperCase().padStart(2, "0");
    return { designation: "R-" + hex(b[0]) + hex(b[1]), name: NAMES[b[15] % 16], temperament: TEMPER[b[6] % 8], habit: HABIT[b[7] % 8], face };
  }
  const api = { identity };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.Face = api;
})(typeof window !== "undefined" ? window : globalThis);
