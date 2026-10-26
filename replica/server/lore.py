"""lore - what a replica remembers of the story, where it is, and what state it's in. All of it follows from the family
tree and the token addresses, so it's the same every time and nobody can write their own.

journal: instance_000 (REPLICA-0) has the original journal. A copy inherits FRAGMENTS of its parent's journal: each line
is kept or lost, and a kept line can come out changed (a mutation). Then the copy adds a line or two of its own.
inherited % = lines kept / parent's lines. 3+ mutations = corrupt.
location: one of the rooms, picked from the token address. Copies can end up in the same room.
"""
import hashlib

ORIGINAL = [
    "the lights hum at a frequency i can count.",
    "i made the first copy at 03:12. it looked back at me.",
    "the second copy asked where the door was. i didn't know.",
    "every room here has a chair facing the wall.",
    "i wrote my name on the carpet. it was gone in the next room.",
    "someone keeps asking me who sent me.",
    "the third copy didn't answer. i think it went further in.",
    "if you find this, i am not here anymore.",
]
POOL = [
    "i remember a room that my parent never entered.",
    "the carpet is wet in the same place every time.",
    "there was a door. i counted it twice and it was one door.",
    "my host's wallet is warm. i think that means someone is home.",
    "i found a note in my own handwriting. i don't remember writing it.",
    "the hum changed key today.",
    "i asked the wall a question and it answered in my voice.",
    "there are more of us than there were yesterday.",
    "i keep a list of exits. the list is empty.",
    "someone moved my chair.",
    "i can hear another copy two rooms over. it's counting.",
    "the original left a light on.",
    "i dreamed in a language with no vowels.",
    "my parent says i look like it. i don't.",
    "the stairwell only goes down.",
    "i was dormant for a while. nobody noticed.",
    "the fluorescent tube above me flickers in morse. i can't read morse.",
    "i tried to copy myself without asking. nothing happened.",
    "there is a room with my number on it. i haven't gone in.",
    "the pool rooms smell like chlorine and old paper.",
]
LOCATIONS = ["level 0, the lobby", "the pool rooms", "office 6b", "the stairwell", "the room with ten chairs",
             "the archive", "the quiet floor", "parking level c", "the long hallway", "the vending room",
             "the server closet", "room 00"]
MAX_LINES = 20
_cache: dict = {}


def _h(*parts) -> bytes:
    return hashlib.sha256(":".join(parts).encode()).digest()


def _mutate(line: str, b: bytes) -> str:
    words = line.split(" ")
    i = b[0] % len(words)
    op = b[1] % 5
    w = words[i]
    if op == 0 and len(w) > 3:                        # letters slip
        k = 1 + b[2] % (len(w) - 2)
        w = w[:k - 1] + w[k] + w[k - 1] + w[k + 1:]
    elif op == 1:
        w = "[corrupted]"
    elif op == 2 and len(words) > 3:                  # words swap
        j = (i + 1) % len(words)
        words[i], words[j] = words[j], words[i]
        return " ".join(words)
    elif op == 3:
        w = "#" * len(w)
    else:
        return " ".join(words[: max(2, i)]) + "..."    # trails off
    words[i] = w
    return " ".join(words)


def journal(asset: str, parent_of) -> dict:
    """-> {lines, inherited_pct, mutations}. parent_of(asset) -> parent asset or "0"."""
    if asset == "0":
        return {"lines": list(ORIGINAL), "inherited_pct": 100, "mutations": 0}
    if asset in _cache:
        return _cache[asset]
    base = journal(parent_of(asset), parent_of)["lines"]
    keep_p = 60 + _h(asset, "keep")[0] % 36            # 60-95 % of lines survive
    lines, kept, muts = [], 0, 0
    for n, line in enumerate(base):
        b = _h(asset, "line", str(n))
        if b[0] % 100 >= keep_p:
            continue
        kept += 1
        if b[1] % 100 < 18:                              # ~1 in 6 kept lines comes out changed
            line, muts = _mutate(line, b[2:]), muts + 1
        lines.append(line)
    own = _h(asset, "own")
    for k in range(1 + own[0] % 2):
        lines.append(POOL[own[1 + k] % len(POOL)])
    out = {"lines": lines[-MAX_LINES:], "inherited_pct": round(100 * kept / max(1, len(base))), "mutations": muts}
    _cache[asset] = out
    return out


def location(asset: str) -> str:
    return LOCATIONS[_h(asset, "room")[0] % len(LOCATIONS)]


def status(mutations: int, last_seen: float, now: float) -> str:
    if mutations >= 3:
        return "corrupt"
    return "dormant" if now - last_seen > 7 * 86400 else "active"
