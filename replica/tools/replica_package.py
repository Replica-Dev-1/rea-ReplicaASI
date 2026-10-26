"""Assemble a reviewed skill spec from bounded local text files; never executes them."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
import skills


def assemble(spec_path):
    spec_path = Path(spec_path)
    if spec_path.is_symlink() or spec_path.stat().st_size > 100_000:
        raise ValueError("Skill spec must be a regular file of at most 100 KB.")
    package = json.loads(spec_path.read_text(encoding="utf-8"))
    if not isinstance(package, dict) or not isinstance(package.get("files"), list) or not 1 <= len(package["files"]) <= 32:
        raise ValueError("Skill spec must list 1-32 files.")
    base = spec_path.parent.resolve()
    embedded, total = [], 0
    for item in package["files"]:
        if not isinstance(item, dict):
            raise ValueError("Invalid file specification.")
        name = item.get("path", "")
        if not isinstance(name, str) or not skills.PATH.fullmatch(name) or ".." in name:
            raise ValueError("Only safe relative file paths may be packaged.")
        path = base / name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(base):
            raise ValueError("Package files must remain inside the build folder.")
        if path.stat().st_size > 1_000_000:
            raise ValueError("An embedded file exceeds 1 MB.")
        content = path.read_bytes().decode("utf-8")
        total += len(content.encode("utf-8"))
        if total > skills.MAX_BYTES:
            raise ValueError("Package contents exceed 1.5 MB.")
        embedded.append({"path": name, "role": item.get("role"), "content": content,
                         "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()})
    package["files"] = embedded
    raw = json.dumps(package, ensure_ascii=False, indent=2) + "\n"
    skills.validate(raw)
    return raw


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec")
    parser.add_argument("output")
    args = parser.parse_args()
    raw = assemble(args.spec)
    with Path(args.output).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(raw)
    print("Validated package saved. Its test record is author-reported; no code was executed by this assembler.")
