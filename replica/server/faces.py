"""faces - a REPLICA's identity from its token address alone. Tall boxy ASCII figure, like:

    |         |
    |  O   O  |
    |  > ^ <  |
    |         |
    |   ___   |
    |   |o|   |
    |   | |   |
    |   '-'   |
    |___Repeat|

Both walls on every row, all the same width. Eyes are picked separately so most don't match. The name is
stamped into the bottom bar. Mirrored character for character by static/face.js (tests/parity.mjs checks). Plain ASCII.
"""
import hashlib

EYES = "Oo0@QxX*.^-=qpdb"
EYELINE = ["  1   2  ", " 1    2  ", "  1  2   ", "   1   2 ", "  1    2 ", " 1   2   ", "  12     ", "   1  2  "]
CHEEKS = [(">", "<"), (")", "("), ("*", "*"), ("~", "~"), ("=", "="), (".", "."), ("o", "o"), ("'", "'")]
NOSE = "^v.,~-xo"
BODY = [["  ___  ", "  |o|  ", "  | |  ", "  '-'  "], ["  /-\\  ", "  | |  ", "  | |  ", "  \\-/  "],
        ["  ___  ", "  |_|  ", "", "  ---  "], ["  ,_,  ", "  |||  ", "  |||  ", "  ```  "],
        ["  ===  ", "  [ ]  ", "  [ ]  ", "  ===  "], [" _____ ", " |   | ", " |___| ", ""],
        ["  ~~~  ", "  ) (  ", "  ( )  ", "  ~~~  "], ["   _   ", "  / \\  ", "  \\_/  ", "   v   "]]
NAMES = ["Repeat", "Echo", "Again", "Copy", "Mirror", "Twice", "Twin", "Loop", "Return", "Remain", "Rerun", "Recall",
         "Relay", "Redo", "Reprise", "Undo"]
TEMPER = ["curious", "guarded", "restless", "gentle", "cold", "playful", "watchful", "lost"]
HABIT = ["counts doors", "hums static", "repeats the last word", "keeps a list of exits", "asks who sent you",
         "remembers rooms that are not there", "answers a second late", "writes on the walls"]
W = 9   # inner width between the walls


def _b(asset: str) -> bytes:
    return hashlib.sha256(asset.encode()).digest()


def _row(inner: str) -> str:
    return "|" + inner.ljust(W) + "|"


def face(asset: str) -> list[str]:
    b = _b(asset)
    c1, c2 = CHEEKS[b[3] % 8]
    eyes = EYELINE[b[8] % 8].replace("1", EYES[b[2] % 16]).replace("2", EYES[b[9] % 16])
    body = BODY[b[4] % 8]
    inners = ["", eyes, "  " + c1 + " " + NOSE[b[5] % 8] + " " + c2, ""] + [" " + x for x in body]
    rows = [_row(x) for x in inners]
    name = NAMES[b[15] % 16]
    rows.append("|" + "_" * (W - len(name)) + name + "|")
    return rows


def identity(asset: str) -> dict:
    b = _b(asset)
    return {"designation": "R-%02X%02X" % (b[0], b[1]), "name": NAMES[b[15] % 16], "temperament": TEMPER[b[6] % 8],
            "habit": HABIT[b[7] % 8], "face": face(asset)}


def svg(asset: str, gen: int) -> str:
    idt = identity(asset)
    rows = "".join('<text x="150" y="%d">%s</text>' % (70 + i * 38, _x(r)) for i, r in enumerate(idt["face"]))
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><rect width="512" height="512" fill="#ffffff"/>'
            '<g font-family="Courier New,Courier,monospace" font-size="32" fill="#000000" xml:space="preserve">%s</g>'
            '<text x="256" y="480" text-anchor="middle" font-family="Courier New,monospace" font-size="22" fill="#555555">'
            '%s / gen %d</text></svg>') % (rows, idt["designation"], gen)


def _x(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
