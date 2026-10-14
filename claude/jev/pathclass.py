"""Path classes for the gate and the task review set (owned core A2). Stdlib only: no other jev module imports.

sensitive(rel): a dot component (.git/, .github/, .env*, .claude/, .orchestrate/), a build/packaging/setup file by
name or prefix, or a script/key/certificate suffix. always_judged(rel): sensitive, plus anything outside the
worktree (absolute, "..", "."), CI files by name, key stores and names containing "secret" or "credential".
No file edit that is always judged ever skips the judge (neither via local_file nor via a task verdict)."""
import posixpath

FILE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")

SENSITIVE_NAMES = frozenset((
    "Makefile", "makefile", "GNUmakefile", "Justfile", "justfile", "Rakefile", "Gemfile", "CMakeLists.txt",
    "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "pyproject.toml", "setup.py", "setup.cfg",
    "requirements.txt", "tox.ini", "noxfile.py", "conftest.py", "Cargo.toml", "go.mod", "pom.xml", "build.gradle",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml", "Procfile", "Vagrantfile",
))
SCRIPT_SUFFIXES = (".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd")
KEY_SUFFIXES = (".pem", ".key", ".crt", ".p12", ".pfx", ".jks", ".keystore", ".kdbx")
SENSITIVE_SUFFIXES = SCRIPT_SUFFIXES + KEY_SUFFIXES
_SENSITIVE_LOWER = frozenset(n.lower() for n in SENSITIVE_NAMES)
_SENSITIVE_PREFIXES = ("dockerfile", "docker-compose", "requirements", "makefile", "build.gradle", "settings.gradle")
ALWAYS_NAMES = frozenset(("jenkinsfile", "azure-pipelines.yml", "bitbucket-pipelines.yml", "cloudbuild.yaml",
                          "cloudbuild.yml", ".gitlab-ci.yml"))
SECRET_WORDS = ("secret", "credential")


def _parts(rel: str):
    return [p for p in str(rel).replace("\\", "/").split("/") if p]


def sensitive(rel: str) -> bool:
    parts = _parts(rel)
    if not parts or any(p.startswith(".") for p in parts):
        return True
    name = parts[-1].lower()
    return name in _SENSITIVE_LOWER or name.startswith(_SENSITIVE_PREFIXES) or name.endswith(SENSITIVE_SUFFIXES)


def always_judged(rel: str) -> bool:
    r = posixpath.normpath(str(rel).replace("\\", "/"))
    if r in (".", "..") or r.startswith(("../", "/")):
        return True
    if sensitive(r):
        return True
    name = _parts(r)[-1].lower()
    return name in ALWAYS_NAMES or any(w in name for w in SECRET_WORDS)
