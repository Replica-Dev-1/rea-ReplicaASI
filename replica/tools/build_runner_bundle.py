"""Build the public companion download from an explicit list; no private state or dependencies."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "tools/replica_runner.py", "tools/replica_agent.py", "tools/replica_package.py", "tools/unpack_skill.py",
    "server/skills.py", "integrations/rea/package.json",
    "agents/replica/agent.json",
    "samples/notes-target/search.cjs", "samples/notes-target/LICENSE.txt",
    "static/samples/search/parent.skill.json", "static/samples/search/child.skill.json",
]

if __name__ == "__main__":
    guide = (ROOT / "integrations/rea/RUNNER.md").read_bytes()
    for name in FILES:
        if not (ROOT / name).is_file():
            raise FileNotFoundError(name)
    destination = ROOT / "static/runner"
    with ZipFile(destination / "replica-runner.zip", "w", ZIP_DEFLATED) as bundle:
        for name in FILES:
            bundle.write(ROOT / name, name)
        bundle.writestr("README.txt", guide)
    (destination / "guide.txt").write_bytes(guide)
    print("Runner bundle includes all build helpers and the setup guide.")
