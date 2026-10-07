"""
Slopsquatting Shield - prototype core.

Checks packages in an install command (pip / npm / yarn / pnpm) BEFORE you run it.
Verdicts: BLOCK (red), WARN (yellow), ALLOW (green), UNKNOWN (could not check).

Usage:
    python shield.py "pip install requests some-fake-package"
"""
import difflib
import json
import re
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

HERE = Path(__file__).parent
TIMEOUT = 15

# Score thresholds
BLOCK_AT = 60
WARN_AT = 25

POPULAR = {
    "pypi": [
        "requests", "numpy", "pandas", "flask", "django", "fastapi", "pytest",
        "scipy", "matplotlib", "pillow", "beautifulsoup4", "selenium", "pypdf",
        "openpyxl", "sqlalchemy", "pydantic", "httpx", "aiohttp", "scikit-learn",
        "tensorflow", "torch", "opencv-python", "python-dotenv", "pyjwt", "uvicorn",
        "streamlit", "rich", "click", "typer", "boto3", "cryptography", "lxml",
    ],
    "npm": [
        "express", "react", "lodash", "axios", "moment", "chalk", "commander",
        "dotenv", "jsonwebtoken", "bcrypt", "mongoose", "cors", "nodemon",
        "typescript", "webpack", "vite", "next", "vue", "zod", "uuid", "pg",
        "socket.io", "body-parser", "cheerio", "puppeteer", "jest",
    ],
}


# ---------------------------------------------------------------- hallucination DB
def load_hallucination_db():
    """name -> 'did you mean' (may be empty string). Edit hallucinated_names.json."""
    path = HERE / "hallucinated_names.json"
    if not path.exists():
        return {"pypi": {}, "npm": {}}
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {
        "pypi": {normalize(k, "pypi"): v for k, v in raw.get("pypi", {}).items()},
        "npm": {normalize(k, "npm"): v for k, v in raw.get("npm", {}).items()},
    }


def normalize(name, eco):
    name = name.strip().lower()
    if eco == "pypi":
        name = re.sub(r"[-_.]+", "-", name)  # PEP 503
    return name


# ---------------------------------------------------------------- parsing
PIP_VALUE_OPTS = {"-r", "-c", "-e", "-i", "-t", "--index-url", "--extra-index-url",
                  "--target", "--requirement", "--constraint", "--editable"}


def _is_local_or_url(arg):
    return (arg.startswith((".", "/", "~", "git+", "http", "file:"))
            or arg.endswith((".txt", ".whl", ".tar.gz", ".zip")))


def parse_command(text):
    """Return a list of (ecosystem, package_name) found in the text."""
    found = []
    for line in re.split(r"[\n;&|]+", text):
        line = line.strip().lstrip("$ ").strip()
        if not line:
            continue
        try:
            tokens = shlex.split(line)
        except ValueError:
            tokens = line.split()

        for i, tok in enumerate(tokens):
            tool = tok.split("/")[-1].lower()
            nxt = tokens[i + 1].lower() if i + 1 < len(tokens) else ""
            eco = None
            if tool in ("pip", "pip3") and nxt == "install":
                eco = "pypi"
            elif tool in ("npm", "pnpm") and nxt in ("install", "i", "add"):
                eco = "npm"
            elif tool == "yarn" and nxt == "add":
                eco = "npm"
            if not eco:
                continue

            args = tokens[i + 2:]
            skip_next = False
            for arg in args:
                if skip_next:
                    skip_next = False
                    continue
                if eco == "pypi" and arg in PIP_VALUE_OPTS:
                    skip_next = True
                    continue
                if arg.startswith("-") or _is_local_or_url(arg):
                    continue
                found.append((eco, _strip_version(arg, eco)))
            break
    # de-duplicate, keep order
    seen, unique = set(), []
    for item in found:
        if item not in seen and item[1]:
            seen.add(item)
            unique.append(item)
    return unique


def _strip_version(arg, eco):
    if eco == "pypi":
        return re.split(r"[=<>!~;\[ ]", arg)[0]
    if arg.startswith("@"):  # scoped npm package: @scope/name@1.2.3
        return "@" + arg[1:].split("@")[0]
    return arg.split("@")[0]


# ---------------------------------------------------------------- registry lookups
def _parse_time(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _days_since(dt):
    return (datetime.now(timezone.utc) - dt).days


def fetch_pypi(name):
    r = requests.get(f"https://pypi.org/pypi/{name}/json", timeout=TIMEOUT)
    if r.status_code == 404:
        return {"exists": False}
    r.raise_for_status()
    data = r.json()

    uploads = [_parse_time(f["upload_time_iso_8601"])
               for files in data.get("releases", {}).values() for f in files]
    urls = list((data["info"].get("project_urls") or {}).values())
    urls.append(data["info"].get("home_page") or "")
    has_repo = any(re.search(r"(github|gitlab|bitbucket)\.", u or "", re.I) for u in urls)

    return {
        "exists": True,
        "age_days": _days_since(min(uploads)) if uploads else None,
        "releases": sum(1 for files in data.get("releases", {}).values() if files),
        "has_repo": has_repo,
        "install_script": None,  # PyPI does not expose this in its JSON
        "maintainers": None,
    }


def fetch_npm(name):
    safe = requests.utils.quote(name, safe="@")
    r = requests.get(f"https://registry.npmjs.org/{safe}", timeout=TIMEOUT)
    if r.status_code == 404:
        return {"exists": False}
    r.raise_for_status()
    data = r.json()

    created = data.get("time", {}).get("created")
    latest = data.get("dist-tags", {}).get("latest")
    scripts = (data.get("versions", {}).get(latest, {}) or {}).get("scripts", {}) or {}
    has_install_script = any(k in scripts for k in ("preinstall", "install", "postinstall"))

    return {
        "exists": True,
        "age_days": _days_since(_parse_time(created)) if created else None,
        "releases": len(data.get("versions", {})),
        "has_repo": bool(data.get("repository")),
        "install_script": has_install_script,
        "maintainers": len(data.get("maintainers", [])),
    }


# ---------------------------------------------------------------- scoring
def score_package(info, name, eco, db):
    """Return (score, verdict, reasons). reasons = list of (points, text)."""
    key = normalize(name, eco)
    reasons = []

    if not info["exists"]:
        reasons.append((100, "Package does NOT exist in the registry - an AI likely invented this name."))
        return 100, "BLOCK", reasons

    score = 0
    if key in db[eco]:
        reasons.append((40, "Name is in our database of names AI models commonly invent."))
        score += 40

    age = info.get("age_days")
    if age is not None:
        if age < 30:
            reasons.append((25, f"Very new: first published only {age} day(s) ago."))
            score += 25
        elif age < 180:
            reasons.append((10, f"Fairly new: first published {age} days ago."))
            score += 10

    if not info.get("has_repo"):
        reasons.append((15, "No linked source-code repository (GitHub/GitLab)."))
        score += 15

    if info.get("releases", 0) <= 2:
        reasons.append((10, f"Almost no history: only {info.get('releases', 0)} release(s)."))
        score += 10

    if info.get("install_script"):
        reasons.append((10, "Runs a script automatically at install time."))
        score += 10

    if info.get("maintainers") == 1 and age is not None and age < 180:
        reasons.append((5, "Single maintainer on a young package."))
        score += 5

    if age is not None and age > 365 and info.get("releases", 0) >= 10:
        reasons.append((-30, f"Established: {age // 365}+ year(s) old with {info['releases']} releases."))
        score -= 30

    score = max(score, 0)
    verdict = "BLOCK" if score >= BLOCK_AT else "WARN" if score >= WARN_AT else "ALLOW"
    return score, verdict, reasons


def suggest(name, eco, db):
    """Best-guess 'did you mean' for a missing or risky package."""
    hint = db[eco].get(normalize(name, eco))
    if hint:
        return hint
    close = difflib.get_close_matches(normalize(name, eco), POPULAR[eco], n=1, cutoff=0.7)
    return close[0] if close else ""


# ---------------------------------------------------------------- main entry
def analyze(text):
    """Analyze an install command. Returns a list of result dicts."""
    db = load_hallucination_db()
    results = []
    for eco, name in parse_command(text):
        try:
            info = fetch_pypi(name) if eco == "pypi" else fetch_npm(name)
        except requests.RequestException as e:
            results.append({"ecosystem": eco, "name": name, "verdict": "UNKNOWN", "score": None,
                            "reasons": [(0, f"Could not reach the registry ({type(e).__name__}). Check your internet.")],
                            "did_you_mean": "", "info": {}})
            continue

        score, verdict, reasons = score_package(info, name, eco, db)
        results.append({
            "ecosystem": eco, "name": name, "verdict": verdict, "score": score,
            "reasons": reasons,
            "did_you_mean": suggest(name, eco, db) if verdict in ("BLOCK", "WARN") else "",
            "info": info,
        })
    return results


# ---------------------------------------------------------------- CLI
COLORS = {"BLOCK": "\033[91m", "WARN": "\033[93m", "ALLOW": "\033[92m", "UNKNOWN": "\033[90m"}
RESET, BOLD = "\033[0m", "\033[1m"


def main():
    if len(sys.argv) < 2:
        print('Usage: python shield.py "pip install requests some-package"')
        sys.exit(1)
    results = analyze(" ".join(sys.argv[1:]))
    if not results:
        print("No install command found in that text.")
        return
    print(f"\n{BOLD}Slopsquatting Shield - checking {len(results)} package(s){RESET}\n")
    for r in results:
        c = COLORS[r["verdict"]]
        score = "" if r["score"] is None else f"  (risk score {r['score']})"
        print(f"{c}{BOLD}[{r['verdict']}]{RESET} {BOLD}{r['name']}{RESET} ({r['ecosystem']}){score}")
        for pts, text in r["reasons"]:
            sign = f"{pts:+d}" if pts else "  "
            print(f"   {sign:>4}  {text}")
        if r["verdict"] == "ALLOW" and not r["reasons"]:
            print("         No risk signals found.")
        if r["did_you_mean"]:
            print(f"   {BOLD}Did you mean:{RESET} {r['did_you_mean']}")
        print()
    if any(r["verdict"] == "BLOCK" for r in results):
        print(f"{COLORS['BLOCK']}{BOLD}Do NOT run this command as written.{RESET}\n")


if __name__ == "__main__":
    main()
