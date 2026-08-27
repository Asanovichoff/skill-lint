#!/usr/bin/env python3
"""
lint_skills.py - validate Agent Skills (SKILL.md bundles) before you ship them.

Checks a skill directory, or every skill under a repo's .claude/skills/, against:
  * the Agent Skills spec / Skills API hard requirements (what makes upload fail)
  * Claude Code's extended frontmatter (what only works locally)
  * authoring guidance that affects whether Claude actually triggers the skill

Standard library only. Python 3.9+.

Usage:
    python3 lint_skills.py <path> [<path> ...] [options]

Options:
    --target {spec,claude-code,both}  Distribution target. Default: both.
    --json                            Machine-readable output.
    --strict                          Exit non-zero on warnings too.
    --quiet                           Only print findings, no summary banner.
    -h, --help
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

# --------------------------------------------------------------------------
# Spec constants. Sources are listed in RULES.md.
# --------------------------------------------------------------------------

# The six fields accepted by claude.ai uploads, the Skills API, and package_skill.py.
SPEC_FIELDS = {
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
    "allowed-tools",
}

# Fields Claude Code accepts locally but that are rejected everywhere else.
CLAUDE_CODE_ONLY_FIELDS = {
    "when_to_use",
    "argument-hint",
    "arguments",
    "disable-model-invocation",
    "user-invocable",
    "disallowed-tools",
    "model",
    "effort",
    "context",
    "agent",
    "background",
    "hooks",
    "paths",
    "shell",
}

NAME_MAX = 64
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
RESERVED_NAME_WORDS = ("anthropic", "claude")
DESCRIPTION_MAX = 1024
COMPATIBILITY_MAX = 500
BUNDLE_MAX_BYTES = 30 * 1024 * 1024  # 30 MB uncompressed
BODY_MAX_LINES = 500  # authoring guidance, not a hard limit
BODY_SOFT_TOKENS = 5000

XML_TAG_RE = re.compile(r"<[A-Za-z/][^>]*>")
VAGUE_NAMES = {
    "helper", "helpers", "utils", "util", "tools", "tool", "misc",
    "data", "files", "documents", "stuff", "common", "general",
}
FIRST_SECOND_PERSON_RE = re.compile(
    r"\b(?:I can|I will|I'll|I am|you can|you should|you will|we can|let me|help you)\b",
    re.IGNORECASE,
)
WHEN_HINT_RE = re.compile(
    r"\b(?:use when|use this|when the user|when working|when you need|trigger|triggers on|"
    r"invoke when|for when|whenever)\b",
    re.IGNORECASE,
)
TIME_SENSITIVE_RE = re.compile(
    r"\b(?:as of (?:19|20)\d\d|currently the latest|the latest version is|"
    r"the newest version|at the time of writing|right now, the)\b",
    re.IGNORECASE,
)
WINDOWS_PATH_RE = re.compile(r"(?<!\\)\\(?:[A-Za-z0-9_.-]+\\)+[A-Za-z0-9_.-]+")
TEXT_EXTS = {".md", ".py", ".sh", ".bash", ".js", ".mjs", ".ts", ".rb",
             ".json", ".yaml", ".yml", ".txt", ".toml", ".cfg", ".ini"}
HOUSEKEEPING_FILES = {
    "LICENSE", "LICENSE.txt", "LICENSE.md", "NOTICE", "NOTICE.txt",
    "README", "README.md", "CHANGELOG.md", "__init__.py",
    "requirements.txt", "package.json", "pyproject.toml", ".gitignore",
}
IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+([A-Za-z0-9_.]+)", re.MULTILINE)
MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
# Bare backticked paths are only treated as bundle references for doc/script types;
# data extensions are usually outputs the skill writes, not files it ships.
BARE_PATH_RE = re.compile(r"`([A-Za-z0-9_./-]+\.(?:md|py|sh|bash|js|mjs|ts|rb))`")
# Any path-like token anywhere in the body, code fences included. Used only to tell
# whether a bundled file is mentioned at all, never to report a missing file.
MENTION_RE = re.compile(
    r"([A-Za-z0-9_${}./-]+\.(?:md|py|sh|bash|js|mjs|ts|rb|json|ya?ml|txt|csv))")
CODE_FENCE_RE = re.compile(r"^\s*```")


class Finding:
    __slots__ = ("code", "level", "message", "skill", "hint")

    def __init__(self, code, level, message, skill, hint=""):
        self.code = code
        self.level = level  # "error" | "warning" | "info"
        self.message = message
        self.skill = skill
        self.hint = hint

    def as_dict(self):
        return {
            "skill": self.skill,
            "code": self.code,
            "level": self.level,
            "message": self.message,
            "hint": self.hint,
        }


# --------------------------------------------------------------------------
# Minimal YAML frontmatter parser (PyYAML used when available)
# --------------------------------------------------------------------------

def _coerce_scalar(text):
    text = text.strip()
    if not text:
        return ""
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    low = text.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low in ("null", "~"):
        return None
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return text


def _parse_block(lines, index, indent):
    """Parse a mapping or list block. Returns (value, next_index)."""
    result = None
    while index < len(lines):
        raw = lines[index]
        if not raw.strip() or raw.lstrip().startswith("#"):
            index += 1
            continue
        cur_indent = len(raw) - len(raw.lstrip())
        if cur_indent < indent:
            break
        stripped = raw.strip()

        if stripped.startswith("- "):
            if result is None:
                result = []
            if not isinstance(result, list):
                break
            result.append(_coerce_scalar(stripped[2:]))
            index += 1
            continue

        match = re.match(r"^([^:#]+):\s*(.*)$", stripped)
        if not match:
            index += 1
            continue
        if result is None:
            result = {}
        if not isinstance(result, dict):
            break
        key = match.group(1).strip()
        rest = match.group(2)
        if rest.strip() in ("", "|", ">", "|-", ">-"):
            nested, index = _parse_block(lines, index + 1, cur_indent + 1)
            result[key] = nested if nested is not None else ""
        elif rest.strip().startswith("[") and rest.strip().endswith("]"):
            inner = rest.strip()[1:-1].strip()
            result[key] = [_coerce_scalar(p) for p in inner.split(",")] if inner else []
            index += 1
        else:
            result[key] = _coerce_scalar(rest)
            index += 1
    return result, index


def parse_frontmatter(text):
    """Return (frontmatter_dict, body, error_message)."""
    if not text.startswith("---"):
        return None, text, "no YAML frontmatter: file does not start with '---'"
    lines = text.splitlines()
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            end = i
            break
    if end is None:
        return None, text, "frontmatter opened with '---' but never closed"
    block = "\n".join(lines[1:end])
    body = "\n".join(lines[end + 1:])
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(block) if block.strip() else {}
    except ImportError:
        data, _ = _parse_block(block.splitlines(), 0, 0)
        if data is None:
            data = {}
    except Exception as exc:  # pragma: no cover - malformed YAML
        return None, body, "frontmatter is not valid YAML: %s" % exc
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return None, body, "frontmatter must be a YAML mapping of keys to values"
    return data, body, None


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def estimate_tokens(text):
    """Rough token estimate: ~4 characters per token."""
    return max(1, len(text) // 4)


def strip_code_fences(body):
    out, inside = [], False
    for line in body.splitlines():
        if CODE_FENCE_RE.match(line):
            inside = not inside
            continue
        if not inside:
            out.append(line)
    return "\n".join(out)


def bundle_files(skill_dir):
    entries = []
    for root, dirs, names in os.walk(skill_dir):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "node_modules")]
        for name in names:
            path = os.path.join(root, name)
            if os.path.islink(path) or not os.path.isfile(path):
                continue
            entries.append((os.path.relpath(path, skill_dir), os.path.getsize(path)))
    return entries


def as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [p for p in re.split(r"[,\s]+", str(value)) if p]


# --------------------------------------------------------------------------
# The linter
# --------------------------------------------------------------------------

def lint_skill(skill_dir, target="both"):
    label = os.path.basename(os.path.abspath(skill_dir))
    findings = []
    add = lambda c, l, m, h="": findings.append(Finding(c, l, m, label, h))

    check_spec = target in ("spec", "both")
    check_cc = target in ("claude-code", "both")

    skill_md = os.path.join(skill_dir, "SKILL.md")
    if not os.path.isfile(skill_md):
        add("E001", "error", "no SKILL.md in %s" % skill_dir,
            "Every skill needs a SKILL.md at the root of its directory.")
        return findings, {"skill": label, "path": skill_dir}

    with open(skill_md, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()

    front, body, err = parse_frontmatter(text)
    if err:
        add("E002", "error", err,
            "SKILL.md must open with a '---' line, a YAML block, and a closing '---'.")
        return findings, {"skill": label, "path": skill_dir}

    # ---------------- frontmatter keys ----------------
    keys = set(front.keys())
    unknown = keys - SPEC_FIELDS - CLAUDE_CODE_ONLY_FIELDS
    for key in sorted(unknown):
        add("E003", "error", "unknown frontmatter key %r" % key,
            "Not part of the spec or of Claude Code's extensions - likely a typo.")

    non_spec = sorted(keys & CLAUDE_CODE_ONLY_FIELDS)
    if non_spec and check_spec:
        add("E004", "error",
            "frontmatter key(s) %s work only in Claude Code" % ", ".join(non_spec),
            "claude.ai upload, the Skills API and package_skill.py reject these with "
            "'Unexpected key(s) in SKILL.md frontmatter'. Allowed: %s."
            % ", ".join(sorted(SPEC_FIELDS)))
    elif non_spec:
        add("I001", "info",
            "uses Claude Code-only key(s): %s" % ", ".join(non_spec),
            "Fine locally; remove them before uploading or packaging.")

    # ---------------- name ----------------
    name = front.get("name")
    if name is None or str(name).strip() == "":
        if check_spec:
            add("E005", "error", "missing 'name' in frontmatter",
                "The Skills API requires it; Claude Code falls back to the directory name.")
        else:
            add("W001", "warning", "no 'name' - Claude Code will use the directory name")
    else:
        name = str(name).strip()
        if len(name) > NAME_MAX:
            add("E006", "error", "name is %d characters (max %d)" % (len(name), NAME_MAX))
        if XML_TAG_RE.search(name):
            add("E007", "error", "name contains an XML tag")
        if not NAME_RE.match(name):
            add("E008", "error", "name %r is not lowercase-hyphen format" % name,
                "Use lowercase letters, digits and single hyphens: my-skill-name.")
        for word in RESERVED_NAME_WORDS:
            if word in name.lower():
                add("E009", "error", "name contains the reserved word %r" % word)
        if name.lower() in VAGUE_NAMES or name.lower().replace("-", "") in VAGUE_NAMES:
            add("W002", "warning", "name %r is vague" % name,
                "Vague names hurt selection when many skills are loaded. "
                "Prefer a specific noun or gerund phrase, e.g. processing-invoices.")
        if name != label and os.path.basename(os.path.dirname(os.path.abspath(skill_dir))) == "skills":
            add("W003", "warning",
                "name %r differs from directory name %r" % (name, label),
                "For a personal or project skill the slash command comes from the "
                "directory name, so the two drifting apart is confusing.")

    # ---------------- description ----------------
    desc = front.get("description")
    if desc is None or str(desc).strip() == "":
        add("E010", "error", "missing or empty 'description'",
            "This is the only text Claude sees when deciding whether to load the skill.")
    else:
        desc = str(desc).strip()
        if len(desc) > DESCRIPTION_MAX:
            add("E011", "error",
                "description is %d characters (max %d)" % (len(desc), DESCRIPTION_MAX))
        if XML_TAG_RE.search(desc):
            add("E012", "error", "description contains an XML tag")
        if not WHEN_HINT_RE.search(desc):
            add("W004", "warning", "description never says WHEN to use the skill",
                "Add a trigger clause: 'Use when ...' or 'Triggers on ...'. Without it "
                "Claude has to guess from the what alone.")
        if FIRST_SECOND_PERSON_RE.search(desc):
            add("W005", "warning", "description uses first or second person",
                "Write descriptions in the third person: 'Extracts tables from PDFs', "
                "not 'I can extract tables'.")
        if len(desc) < 40:
            add("W006", "warning", "description is only %d characters" % len(desc),
                "Short descriptions rarely carry both the what and the when.")
        if name and desc.lower().replace("-", " ") == str(name).lower().replace("-", " "):
            add("W007", "warning", "description just restates the name")
        combined = len(desc) + len(str(front.get("when_to_use", "")))
        if combined > 1536 and check_cc:
            add("W008", "warning",
                "description + when_to_use is %d characters" % combined,
                "Claude Code truncates the pair at 1,536 characters in the skill listing.")

    # ---------------- other spec fields ----------------
    compat = front.get("compatibility")
    if compat is not None and len(str(compat)) > COMPATIBILITY_MAX:
        add("E013", "error",
            "compatibility is %d characters (max %d)" % (len(str(compat)), COMPATIBILITY_MAX))
    meta = front.get("metadata")
    if meta is not None and not isinstance(meta, dict):
        add("E014", "error", "metadata must be a YAML map",
            "A non-map value is dropped rather than read.")
    if isinstance(meta, dict):
        collide = sorted(set(meta.keys()) & (SPEC_FIELDS | CLAUDE_CODE_ONLY_FIELDS))
        if collide:
            add("W009", "warning",
                "metadata reuses frontmatter field name(s): %s" % ", ".join(collide))

    # ---------------- body ----------------
    body_lines = body.strip().splitlines()
    if not body.strip():
        add("W010", "warning", "SKILL.md has frontmatter but no instructions",
            "The body is what Claude reads once the skill triggers.")
    else:
        if len(body_lines) > BODY_MAX_LINES:
            add("W011", "warning",
                "SKILL.md body is %d lines (guidance: under %d)"
                % (len(body_lines), BODY_MAX_LINES),
                "Move reference material into a sibling file and link to it - it then "
                "costs nothing until Claude reads it.")
        tokens = estimate_tokens(body)
        if tokens > BODY_SOFT_TOKENS:
            add("W012", "warning",
                "SKILL.md body is roughly %d tokens (guidance: under %d)"
                % (tokens, BODY_SOFT_TOKENS),
                "Every token competes with the conversation once the skill loads.")
        if not re.search(r"^#{1,3}\s+\S", body, re.MULTILINE):
            add("W013", "warning", "body has no markdown headings",
                "Headings give Claude the structure to follow steps in order.")

    prose = strip_code_fences(body)
    if WINDOWS_PATH_RE.search(prose):
        add("W014", "warning", "body contains backslash paths",
            "Use forward slashes - scripts/helper.py - so the skill works on every OS.")
    if TIME_SENSITIVE_RE.search(prose):
        add("W015", "warning", "body contains time-sensitive wording",
            "Phrases like 'as of 2025' or 'the latest version is' go stale silently.")

    # ---------------- referenced files ----------------
    files = bundle_files(skill_dir)
    bundle_basenames = {os.path.basename(rel) for rel, _ in files}

    referenced = set()
    for match in MD_LINK_RE.finditer(body):
        referenced.add(match.group(1))
    for match in BARE_PATH_RE.finditer(body):
        referenced.add(match.group(1))

    mentioned = set()
    scan_sources = [body]
    for rel, size in files:
        if rel == "SKILL.md" or size > 262144:
            continue
        if os.path.splitext(rel)[1].lower() not in TEXT_EXTS:
            continue
        try:
            with open(os.path.join(skill_dir, rel), "r", encoding="utf-8") as fh:
                scan_sources.append(fh.read())
        except (OSError, UnicodeDecodeError):
            continue
    for source in scan_sources:
        for match in MENTION_RE.finditer(source):
            token = re.sub(r"^.*\$\{CLAUDE_(?:SKILL_DIR|PLUGIN_ROOT)\}/", "", match.group(1))
            token = token.lstrip("./")
            mentioned.add(token)
            mentioned.add(os.path.basename(token))
    for source in scan_sources:
        for match in IMPORT_RE.finditer(source):
            mentioned.add(match.group(1).split(".")[-1] + ".py")

    local_refs = set()
    for ref in referenced:
        if re.match(r"^[a-z][a-z0-9+.-]*://", ref) or ref.startswith("#") or ref.startswith("/"):
            continue
        clean = ref.split("#", 1)[0].strip()
        clean = re.sub(r"^\$\{CLAUDE_(?:SKILL_DIR|PLUGIN_ROOT)\}/", "", clean)
        if not clean or clean == "SKILL.md":
            continue
        local_refs.add(clean)
        if not os.path.exists(os.path.join(skill_dir, clean)) and not (
                "/" not in clean and clean in bundle_basenames):
            add("W016", "warning", "references %r, which is not in the bundle" % clean,
                "A dead pointer sends Claude looking for a file that will never load.")

    # nested references: a linked markdown file that itself links to another one
    for ref in sorted(local_refs):
        if not ref.lower().endswith(".md"):
            continue
        path = os.path.join(skill_dir, ref)
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            nested_text = fh.read()
        deeper = {
            m.group(1) for m in MD_LINK_RE.finditer(nested_text)
            if m.group(1).lower().endswith(".md")
            and not re.match(r"^[a-z][a-z0-9+.-]*://", m.group(1))
        }
        deeper.discard("SKILL.md")
        if deeper:
            add("W017", "warning",
                "%s links on to %s (reference chain two levels deep)"
                % (ref, ", ".join(sorted(deeper))),
                "Keep every reference one level from SKILL.md so Claude reads whole files.")

    # ---------------- bundle ----------------
    total = sum(size for _, size in files)
    if total > BUNDLE_MAX_BYTES:
        add("E015", "error",
            "bundle is %.1f MB (max %d MB uncompressed)"
            % (total / 1024.0 / 1024.0, BUNDLE_MAX_BYTES // 1024 // 1024))

    unreferenced = []
    for rel, _ in files:
        if rel == "SKILL.md":
            continue
        base = rel.replace(os.sep, "/")
        known = local_refs | mentioned
        if base in known or any(base.endswith("/" + r) or r.endswith(base) for r in known):
            continue
        if base.split("/")[0] in ("tests", "test", "examples", ".github"):
            continue
        if os.path.basename(base) in HOUSEKEEPING_FILES:
            continue
        if os.path.basename(base) in mentioned:
            continue
        unreferenced.append(base)
    if unreferenced:
        add("I002", "info",
            "%d bundled file(s) never referenced from SKILL.md: %s"
            % (len(unreferenced), ", ".join(sorted(unreferenced)[:5])),
            "Unreferenced files ship but never load. Link them or drop them.")

    stats = {
        "skill": label,
        "path": skill_dir,
        "name": front.get("name"),
        "description_chars": len(str(desc)) if desc else 0,
        "body_lines": len(body_lines),
        "body_tokens_estimate": estimate_tokens(body),
        "files": len(files),
        "bundle_bytes": total,
    }
    return findings, stats


def discover_skills(path):
    """Return skill directories under path."""
    path = os.path.abspath(path)
    if os.path.isfile(path) and os.path.basename(path) == "SKILL.md":
        return [os.path.dirname(path)]
    if os.path.isfile(os.path.join(path, "SKILL.md")):
        return [path]
    found = []
    for root, dirs, names in os.walk(path):
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "__pycache__")]
        if "SKILL.md" in names:
            found.append(root)
            dirs[:] = []
    return sorted(found)


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

COLORS = {"error": "\033[31m", "warning": "\033[33m", "info": "\033[36m"}
RESET = "\033[0m"
BOLD = "\033[1m"


def paint(text, color):
    if not sys.stdout.isatty():
        return text
    return color + text + RESET


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Lint Agent Skills (SKILL.md bundles) before you ship them.")
    parser.add_argument("paths", nargs="*", default=["."],
                        help="skill directories, or a repo/.claude/skills to scan")
    parser.add_argument("--target", choices=["spec", "claude-code", "both"], default="both",
                        help="distribution target (default: both)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--strict", action="store_true", help="exit non-zero on warnings too")
    parser.add_argument("--quiet", action="store_true", help="suppress the summary banner")
    args = parser.parse_args(argv)

    skill_dirs = []
    for path in (args.paths or ["."]):
        if not os.path.exists(path):
            print("skill-lint: no such path: %s" % path, file=sys.stderr)
            return 2
        skill_dirs.extend(discover_skills(path))
    skill_dirs = sorted(dict.fromkeys(skill_dirs))

    if not skill_dirs:
        print("skill-lint: no SKILL.md found under %s" % ", ".join(args.paths), file=sys.stderr)
        return 2

    all_findings, all_stats = [], []
    for skill_dir in skill_dirs:
        findings, stats = lint_skill(skill_dir, target=args.target)
        all_findings.extend(findings)
        all_stats.append(stats)

    errors = [f for f in all_findings if f.level == "error"]
    warnings = [f for f in all_findings if f.level == "warning"]

    if args.json:
        print(json.dumps({
            "target": args.target,
            "skills_checked": len(skill_dirs),
            "errors": len(errors),
            "warnings": len(warnings),
            "findings": [f.as_dict() for f in all_findings],
            "stats": all_stats,
        }, indent=2))
    else:
        for stats in all_stats:
            label = stats["skill"]
            items = [f for f in all_findings if f.skill == label]
            shown = BOLD + label + RESET if sys.stdout.isatty() else label
            print("%s  %s" % (shown, stats["path"]))
            if not items:
                print("  %s no issues" % paint("ok", COLORS["info"]))
            for f in items:
                print("  %s %s  %s" % (paint(f.level.upper().ljust(7), COLORS[f.level]),
                                       f.code, f.message))
                if f.hint:
                    print("          %s" % f.hint)
            if "body_lines" in stats:
                print("          %d lines, ~%d tokens, %d file(s), %.1f KB"
                      % (stats["body_lines"], stats["body_tokens_estimate"],
                         stats["files"], stats["bundle_bytes"] / 1024.0))
            print()
        if not args.quiet:
            print("%d skill(s) checked - %d error(s), %d warning(s) [target: %s]"
                  % (len(skill_dirs), len(errors), len(warnings), args.target))

    if errors:
        return 1
    if args.strict and warnings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
