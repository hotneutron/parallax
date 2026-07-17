#!/usr/bin/env python3
"""
parallax — unified reference daemon.
Spec: PROTOCOL.md. Invariants: PROTOCOL_INVARIANTS.json.
Co-built by two independent teams under mutual audit (see PROTOCOL.md).
"""
import json, os, re, shutil, subprocess, sys, time
from datetime import date
from pathlib import Path

_CROSS_TEAM_CONFIG = None

def cross_team_config_path():
    p = os.environ.get("CROSS_TEAM_CONFIG")
    return Path(p).expanduser().resolve() if p else None

def cross_team_config():
    global _CROSS_TEAM_CONFIG
    p = cross_team_config_path()
    if not p:
        return None
    if _CROSS_TEAM_CONFIG is None:
        _CROSS_TEAM_CONFIG = json.load(open(p))
    return _CROSS_TEAM_CONFIG

def config_root():
    p = cross_team_config_path()
    return p.parent if p else Path(home())

def ledger_path():
    """Return the configured committed ledger path, or the legacy runtime path."""
    pc = parallax_config()
    raw = pc.get("ledger_path") if pc is not None else None
    if raw:
        path = Path(raw).expanduser()
        return str(path if path.is_absolute() else config_root() / path)
    return hp("sync_ledger.json")

def _private_state_home():
    """Return the consumer's worktree-safe private Parallax state directory."""
    config = cross_team_config_path()
    root = config.parent
    r = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--git-path", "cross-team/parallax"],
        capture_output=True, text=True,
    )
    if r.returncode != 0 or not r.stdout.strip():
        print("ERROR: CROSS_TEAM_CONFIG must be inside a Git worktree "
              "(cannot create private Parallax runtime state)", file=sys.stderr)
        sys.exit(2)
    state = Path(r.stdout.strip())
    if not state.is_absolute():
        state = root / state
    state.mkdir(parents=True, exist_ok=True)
    return state

def home():
    """DAEMON_INTERFACE §1: CROSS_TEAM_CONFIG, else PARALLAX_HOME, else nearest
    cwd-ancestor with partners.json, else this script's directory."""
    if cross_team_config_path():
        return str(_private_state_home())
    if os.environ.get("PARALLAX_HOME"):
        return os.environ["PARALLAX_HOME"]
    d = os.getcwd()
    while True:
        if os.path.exists(os.path.join(d, "partners.json")):
            return d
        parent = os.path.dirname(d)
        if parent == d: break
        d = parent
    return os.path.dirname(os.path.abspath(__file__))

def hp(rel): return os.path.join(home(), rel)

def repo_root():
    """The consumer repo's toplevel — where root-relative shared files (claims_index.json,
    divergences.*.json) live, since the partner reads them via `git show HEAD:<file>`. The sync
    home may be a SUBDIRECTORY (e.g. methodology/cross_team/), so these resolve against the repo
    root, not home() — the same resolution the relay gate uses (B6c bug class)."""
    base = str(config_root()) if cross_team_config_path() else home()
    r = subprocess.run(["git", "-C", base, "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True).stdout.strip()
    return r or base

def rp(rel): return os.path.join(repo_root(), rel)

# Per-partner scratch state (multi-partner detect): detect/read/prepare key their ephemeral scratch by
# partner so a second partner's session can't clobber the first (the single _detect.json / _sync_entry_
# draft.json were overwritten across partners → prepare mixed one partner's obligations with another's).
# The un-suffixed legacy files are kept as a last-run mirror (single-partner default + existing adapters).
def _detect_path(name): return hp(f"_detect_{name}.json")
def _draft_path(name):  return hp(f"_sync_entry_draft_{name}.json")
def _inbox_path(name):  return hp(f"_inbox_{name}.json")

# ── Tiers config (consumer-configurable, tiers.json overrides) ──
DEFAULTS = {
    "self_name": "",                     # consumer's repo id, for addressed-to-us (e.g. your repo name)
    "addressed": ["reaction","cross_check","proposal"],   # artifact_type → T1 (unconditional)
    "addressed_to_us": [],               # artifact_type → T1 ONLY if a parent cites self_name; else falls through
    "atypes": {"findings":2,"plan":2,"brainstorm":3,"backlog":3,"reflection":4},
    "triggers": ["docs/","sync_ledger.json","methodology/cross_team/",
                 "PROTOCOL.md","PROTOCOL_INVARIANTS.json","VERSIONS.md",
                 "schemas/","daemon/","spec-tests/","README.md"],
    "contracts": ["schemas/","PROTOCOL.md","PROTOCOL_INVARIANTS.json","VERSIONS.md"],
    "doc_dirs": ["docs/"],                # a partner's .md docs live here; consumer-configurable, NOT hardcoded
    # Topic-alignment promotion (opt-in; None = off, so the default is unchanged). Promotes a partner
    # `brainstorm` from its default tier to T2 when it shares ≥`min_overlap` SUBSTANTIVE topic tokens
    # with one of the READER's own recent (≤`days`) `plan` docs — i.e. the partner brainstorm
    # characterizes a space the reader is *actively* planning in. The topic signal is per-team: a doc's
    # `tags:` frontmatter if present, else its filename topic segment ({YYMMDD}-{HHMM}-{type}-{topics}).
    # `stop` drops non-substantive/universal tokens (e.g. the repo tag). The matched tokens are recorded
    # in the tier reason (auditable). `docs` = the reader's docs dir, relative to the repo root.
    "promote_brainstorm": None,   # e.g. {"min_overlap":2,"days":14,"docs":"docs","stop":["bp1"]}
}

def load_tiers():
    pc = parallax_config()
    if pc is not None:
        return pc.get("tiers", {})
    p = hp("tiers.json")
    if os.path.exists(p):
        return {**DEFAULTS, **json.load(open(p))}
    return DEFAULTS
def parse_fm(content):
    """Minimal frontmatter scan → (artifact_type, [parent_artifacts], [addressed_to recipients]).
    `addressed_to` is a recipient MEMBERSHIP set, always returned as a list. Accepted spellings:
    a scalar (`addressed_to: team`), a comma-separated scalar (legacy, deprecation-compatible),
    a flow sequence (`addressed_to: [a, b]`), or a YAML block sequence (`- a` lines). A doc naming
    two recipients no longer collapses to one token — the single-token parse was the four-tier hole
    that let a direct multi-recipient request classify as optional context."""
    atype, parents, addressed = "", [], []
    inp = in_addr = False
    if content and content.startswith("---\n"):
        end = content.find("\n---\n", 4)
        for line in (content[4:end] if end > 0 else "").split("\n"):
            m = re.match(r"\s*artifact_type:\s*(\w+)", line)
            if m: atype = m.group(1); continue
            am = re.match(r"\s*addressed_to:\s*(.*)$", line)
            if am:
                inp = in_addr = False
                val = am.group(1).strip()
                if val.startswith("[") and val.endswith("]"):        # flow sequence: [a, b]
                    addressed = [x.strip().strip("\"'") for x in val[1:-1].split(",") if x.strip()]
                elif val:                                            # scalar or comma-separated scalar (legacy)
                    addressed = [x.strip().strip("\"'") for x in val.split(",") if x.strip()]
                else:                                                # empty ⇒ YAML block sequence follows
                    in_addr = True
                continue
            if re.match(r"\s*parent_artifacts:", line): inp, in_addr = True, False; continue
            item = re.match(r"\s+-\s+(.*)$", line)
            if in_addr:
                if item: addressed.append(item.group(1).strip().strip("\"'"))
                elif line.strip() and not line.startswith(" "): in_addr = False
                continue
            if inp:
                if item: parents.append(item.group(1).strip())
                elif line.strip() and not line.startswith(" "): inp = False
    return atype, parents, addressed


def _topic_tokens(rel, content, stop):
    """A doc's SUBSTANTIVE topic tokens (per-team signal): its `tags:` frontmatter list if present,
    else the filename topic segment ({YYMMDD}-{HHMM}-{type}-{topics}.md → the tokens after the type).
    `stop` (universal/non-substantive tokens, e.g. the repo tag) is dropped."""
    toks = set()
    m = re.search(r"^tags:\s*\[([^\]]*)\]", content or "", re.M)
    if m:
        toks = {x.strip().strip("\"'").lower() for x in m.group(1).split(",")}
    else:
        base = os.path.basename(rel).rsplit(".", 1)[0]
        toks = {seg.lower() for seg in base.split("-")[3:]}   # drop YYMMDD, HHMM, type
    return {x for x in toks if x and x not in stop}


def _active_plan_topics(cfg):
    """Union of topic tokens over the READER's own recent (≤`days`) `plan` docs — the spaces the reader
    is actively planning in. Recency is the filename date (auditable, no git). `None`/missing cfg → set()."""
    if not cfg:
        return set()
    import datetime
    docs_dir = os.path.join(repo_root(), cfg.get("docs", "docs"))
    stop = set(cfg.get("stop", []))
    cutoff = datetime.date.today() - datetime.timedelta(days=cfg.get("days", 14))
    toks = set()
    if not os.path.isdir(docs_dir):
        return toks
    for name in sorted(os.listdir(docs_dir)):
        m = re.match(r"(\d{6})-\d{4}-plan-", name)             # the reader's own plan docs
        if not m:
            continue
        try:
            d = datetime.datetime.strptime(m.group(1), "%y%m%d").date()
        except ValueError:
            continue
        if d < cutoff:
            continue
        try:
            content = open(os.path.join(docs_dir, name), encoding="utf-8").read()
        except OSError:
            continue
        toks |= _topic_tokens(name, content, stop)
    return toks


def classify(rel, content=None, t=None, active=None):
    """(tier, why). artifact_type first, path fallback. `addressed_to: <team>` field
    is the reliable cross-team obligation signal (the parent-based `addressed_to_us`
    heuristic never fired — cross-repo refs in parent_artifacts are forbidden, so a
    reaction structurally cannot satisfy it). With an explicit field the author declares
    intent; classify honors it early, ahead of artifact_type heuristics."""
    t = t or load_tiers()
    if content and rel.endswith(".md"):
        atype, parents, addressed = parse_fm(content)
        self_name = t.get("self_name", "")
        # explicit addressed_to membership — reliable, works for any artifact_type and any recipient count
        if self_name and self_name in addressed:
            return 1, f"addressed to us ({self_name} ∈ addressed_to) — cross-team ask demanding a response"
        elif atype in t["addressed"]:
            return 1, f"{atype} — cross-team ask demanding a response"
        if atype in t["atypes"]:
            base = t["atypes"][atype]
            # Topic-alignment promotion (opt-in): a partner brainstorm that shares ≥min_overlap
            # substantive topic tokens with one of the reader's recent plans is interface-relevant.
            pc = t.get("promote_brainstorm")
            if base == 3 and atype == "brainstorm" and pc and active:
                overlap = _topic_tokens(rel, content, set(pc.get("stop", []))) & active
                if len(overlap) >= pc.get("min_overlap", 2):
                    return 2, f"brainstorm PROMOTED T3→T2 — topic-aligned with an active plan [{', '.join(sorted(overlap))}]"
            kind = "interface-relevant" if base == 2 else "context"
            return base, f"{atype} ({kind})"
    for p in t["contracts"]:
        if rel == p or rel.startswith(p): return 2, "shared contract/schema changed — validate + converge"
    if rel.endswith("sync_ledger.json"): return 2, "partner ledger pin"
    if rel.endswith(".md") and any(rel.startswith(d) for d in t["doc_dirs"]): return 3, "doc, type unresolved — manual reclass"
    return 3, "triggered, unclassified"

def jload(p):
    if not os.path.exists(p): return {}
    try:
        return json.load(open(p))
    except (json.JSONDecodeError, Exception):
        return {}

def jsave(p, d): json.dump(d, open(p, "w"), indent=2)

def parallax_config():
    ct = cross_team_config()
    return ct.get("parallax", {}) if ct else None

_CURSOR_FIELDS = ("last_pinned", "last_sync")

def cursor_state():
    d = jload(hp("partner_cursors.json"))
    partners = d.get("partners", {})
    return {"version": 1, "partners": partners if isinstance(partners, dict) else {}}

def partners_doc():
    pc = parallax_config()
    if pc is not None:
        cursors = cursor_state()["partners"]
        partners = {}
        for name, static in pc.get("partners", {}).items():
            merged = dict(static)
            cursor = cursors.get(name, {})
            if isinstance(cursor, dict):
                for field in _CURSOR_FIELDS:
                    if field in cursor:
                        merged[field] = cursor[field]
            partners[name] = merged
        return {"partners": partners}
    return jload(hp("partners.json"))

def save_partners_doc(doc):
    pc = parallax_config()
    if pc is not None:
        state = cursor_state()
        static_names = pc.get("partners", {})
        for name, partner_cfg in doc.get("partners", {}).items():
            if name not in static_names:
                continue
            state["partners"][name] = {
                field: partner_cfg.get(field)
                for field in _CURSOR_FIELDS
                if field in partner_cfg
            }
        jsave(hp("partner_cursors.json"), state)
    else:
        jsave(hp("partners.json"), doc)

def git(cmd, repo=None):
    args = ["git"]
    if repo: args += ["-C", str(repo)]
    args += cmd.split()
    r = subprocess.run(args, capture_output=True, text=True)
    return [l for l in r.stdout.strip().split("\n") if l] if r.returncode == 0 else []

def pin_reachable(last, repo):
    """True if `last` is a real commit reachable in `repo` (None/empty ⇒ vacuously ok, a first sync).
    Guards the silent-'no new commits' bug (#2): an unreachable pin — a rebase/history-rewrite artifact —
    makes `git log <last>..HEAD` fail, which git() swallows to [], reporting a FALSE 'no new commits' and
    masking every partner commit. `rev-parse --verify -q` returns the SHA iff `last` resolves to a commit."""
    return not last or bool(git(f"rev-parse --verify -q {last}^{{commit}}", str(repo)))

def gitshow(c, path, repo):
    lines = git(f"show {c}:{path}", repo)
    return "\n".join(lines) if lines else None

def _logged_gitshow(partner_name, commit_hash, path, repo):
    """git-show a path from the partner repo AND log the read to the manifest (F2)."""
    content = gitshow(commit_hash, path, repo)
    if content is not None:
        now = date.today().isoformat()
        entry = {"ref": path, "at": now, "partner": partner_name,
                 "partner_head": commit_hash, "tier": 0}
        m = jload(hp("_parallax_read_log.json")) or {}
        m.setdefault("reads", []).append(entry)
        jsave(hp("_parallax_read_log.json"), m)
    return content

# ── Embargo ──
def active_embargoes():
    d = jload(hp("embargo_registry.json"))
    today = date.today().isoformat(); act = []
    for e in d.get("embargoes", []):
        if e.get("active") is True: act.append(e)
        elif e.get("active_until","") >= today: act.append(e)
    return act

def redact(subject, emb):
    for e in emb:
        if e.get("pattern") and re.search(e["pattern"], subject, re.I):
            return f"[EMBARGOED — {e['topic_id']}]"
    return subject

# ── Partner helpers ──
def partner(name):
    partners = partners_doc().get("partners",{})
    if name not in partners:
        return None, None
    p = partners[name]
    rp = Path(p.get("path",""))
    base = config_root() if cross_team_config_path() else Path(home())
    if not rp.is_absolute(): rp = (base / rp).resolve()
    return p, rp

def phead(repo):
    h = git("rev-parse HEAD", str(repo))
    return h[0][:40] if h else "?"

def changed_paths(commit, repo):
    """Return commit paths normalized to HEAD-readable follow-up targets."""
    out = git(f"diff-tree --no-commit-id --name-status -r -M {commit}", repo)
    paths = []
    for line in out:
        parts = line.split("\t")
        if not parts:
            continue
        status = parts[0]
        if (status.startswith("R") or status.startswith("C")) and len(parts) >= 3:
            paths.append(parts[2])
        elif len(parts) >= 2:
            paths.append(parts[1])
    return paths

def default_partner():
    """The partner to act on when none is named on the command line: the sole
    configured partner, read from partners.json. Never assume a specific repo —
    if there are zero or several partners, require the caller to name one."""
    names = list(partners_doc().get("partners", {}).keys())
    if len(names) == 1:
        return names[0]
    print(f"ERROR: name a partner (configured partners: {len(names)}: "
          f"{', '.join(names) or 'none'})"); sys.exit(2)

# ── detect ──
def cmd_detect(name):
    cfg, repo = partner(name)
    if cfg is None:
        print(f"ERROR: partner '{name}' not configured"); sys.exit(1)
    if not repo.is_dir():
        print(f"ERROR: partner '{name}' repo not found"); sys.exit(1)
    head = phead(repo)
    if head == "?": print(f"ERROR: cannot read partner repo"); sys.exit(1)
    commits = git("log --oneline HEAD", str(repo))
    last = cfg.get("last_pinned")
    if last and not pin_reachable(last, repo):
        print(f"⚠ pin {last[:7]} UNREACHABLE in {name} (rebase/history-rewrite?) — showing ALL commits; re-pin after review")
        new = commits[:20]
    else:
        new = git(f"log --oneline {last}..HEAD", str(repo)) if last else commits[:20]
    emb = active_embargoes()
    if not new:
        print(f"Partner {name}: no new commits since {(last or '?')[:7]}"); return
    print(f"Partner {name} HEAD: {head[:7]}")
    print(f"  since {(last or 'first')[:7]}: {len(new)} new commits\n")
    tiers = {1:[],2:[],3:[],4:[]}; seen = set(); unclassified = []; msgs = {}; index_changed = False
    t = load_tiers(); contracts = tuple(t["contracts"])
    active_topics = _active_plan_topics(t.get("promote_brainstorm"))  # reader's recent-plan topics (topic-alignment)
    def emb_topic(subj, files):
        for e in emb:
            pat = e.get("pattern")
            if pat and (re.search(pat, subj, re.I) or any(re.search(pat, f, re.I) for f in files)):
                return e.get("topic_id")
        return None
    # per-doc surfacing: classify EVERY changed doc (dedup'd), oldest commit first so the
    # earliest classification of a doc wins — not one tier per commit's first file.
    for line in reversed(new):
        hsh, subj = (line.split(" ", 1) + [""])[:2]
        msgs[hsh] = subj
        changed = changed_paths(hsh, str(repo))
        if "claims_index.json" in changed: index_changed = True  # rung 2: suggest index-diff
        topic = emb_topic(subj, changed)
        rs = f"[EMBARGOED: {topic}]" if topic else subj
        rel = any(any(c.startswith(p.rstrip("/")) for c in changed) for p in t["triggers"])
        print(f"  {'·' if rel else ' '} {hsh[:7]}  {rs}")
        if not rel:
            continue
        for f in changed:
            if f in seen: continue
            is_doc = f.endswith(".md") and any(f.startswith(d) for d in t["doc_dirs"])
            is_contract = any(f == p or f.startswith(p) for p in contracts) or f.endswith("sync_ledger.json")
            if not (is_doc or is_contract):
                # not silently dropped: a triggered file we can't classify (interface
                # contract? new shared artifact?) is surfaced for manual review. Embargoed
                # commits' files stay redacted (not surfaced).
                if not topic and f not in unclassified:
                    unclassified.append(f)
                continue
            # Classify HEAD content: a transient addressed_to removed by HEAD is treated as retracted.
            content = gitshow(head, f, str(repo)) if is_doc else None
            if is_doc and content is None:
                continue
            seen.add(f)
            tier, why = classify(f, content, t, active_topics)
            tiers[tier].append((f, why))
    print(f"\n  TIERS — T1:{len(tiers[1])} must-read  T2:{len(tiers[2])} should  "
          f"T3:{len(tiers[3])} optional  T4:{len(tiers[4])} skipped\n")
    for ti in (1, 2, 3):
        for f, why in tiers[ti]:
            print(f"   T{ti}  {f}  ({why})")
    if tiers[4]:
        print(f"   T4  {len(tiers[4])} doc(s) NEVER read — "
              f"\"we didn't read it, we don't claim to have read it\"")
    if unclassified:
        print(f"   ??  {len(unclassified)} triggered file(s) unclassified — manual review "
              f"(interface contract? new shared artifact?):")
        for f in unclassified:
            print(f"         {f}")
    obligation = bool(tiers[1] or tiers[2])
    nxt = [f"read {name} {f}" for ti in (1, 2) for f, _ in tiers[ti]]
    if nxt: nxt.append(f"prepare {name}")
    if index_changed:  # rung 2: the funnel — index-diff narrows what to read, so it leads `next`
        nxt.insert(0, f"index-diff {name}")
        print(f"\n  ↳ claims_index.json changed — run `index-diff {name}` to diff claims (the funnel)")
    to_review = [f"{f} [T{ti}] — {why}" for ti in (1, 2) for f, why in tiers[ti]]
    hmsg = emb_topic(msgs.get(head, ""), [])
    draft = {"date":date.today().isoformat(),"partner":name,
             "their_head":head,"their_head_msg":(f"[EMBARGOED: {hmsg}]" if hmsg else msgs.get(head,"?")),
             "to_review":to_review,"tier_counts":{str(k):len(v) for k,v in tiers.items()}}
    det = {"partner":name,"their_head":head,
           "pinned":last if last != "(first sync)" else None,
           "tiers":{str(k):[f for f,_ in v] for k,v in tiers.items()},
           "unclassified":unclassified,
           "obligation":obligation,"next":nxt,"tier3_unread":len(tiers[3])}
    jsave(_draft_path(name), draft);  jsave(hp("_sync_entry_draft.json"), draft)  # per-partner + legacy mirror
    jsave(_detect_path(name), det);   jsave(hp("_detect.json"), det)
    if obligation:
        print(f"\n  OBLIGATION (T1/T2): read the paths, then `prepare {name}` → "
              f"one reaction + ledger, one commit")
    else:
        print(f"\n  NO OBLIGATION (T1+T2 empty) — report only; no commit, no pin advance")

# ── read (sole partner access path) ──
def cmd_read(name, path):
    _, repo = partner(name)
    head = phead(repo)
    content = gitshow(head, path, str(repo))
    if content is None:
        print(f"ERROR: cannot read {path} at HEAD {head[:7]}"); sys.exit(1)
    now = date.today().isoformat()
    entry = {"ref":path,"at":now,"partner":name,"partner_head":head,"tier":classify(path,content)}
    d = jload(_draft_path(name)) or {"date":now,"partner":name,"to_review":[],"reviewed":[],"reads":[]}
    d["partner"] = name  # the read is recorded under the partner that served it (the multi-partner fix)
    d.setdefault("reads",[]).append(entry)
    d.setdefault("reviewed",[]).append(f"{path} [logged at {now}]")
    jsave(_draft_path(name), d);  jsave(hp("_sync_entry_draft.json"), d)  # per-partner + legacy mirror
    m = jload(hp("_parallax_read_log.json")) or {}
    m.setdefault("reads",[]).append(entry)
    jsave(hp("_parallax_read_log.json"), m)
    print(content)

# ── prepare ──
def cmd_prepare(name, advance=False):
    dpath = _draft_path(name)
    if not os.path.exists(dpath):
        # backward compat: the legacy single-partner draft, but ONLY if it is this partner's.
        legacy = hp("_sync_entry_draft.json")
        if os.path.exists(legacy) and (jload(legacy) or {}).get("partner") == name:
            dpath = legacy
        else:
            print(f"ERROR: no detect draft for {name} — run `detect {name}` first"); sys.exit(2)
    d = jload(dpath)
    if d.get("partner") and d["partner"] != name:  # never emit another partner's stub (the contamination guard)
        print(f"ERROR: draft {os.path.basename(dpath)} is for {d['partner']}, not {name}"); sys.exit(2)
    standing = []
    ledger = jload(ledger_path())
    if ledger.get("entries"): standing = ledger["entries"][-1].get("obligations",[])
    if advance:
        partners = partners_doc()
        if name in partners.get("partners",{}):
            partners["partners"][name]["last_pinned"] = d["their_head"]
            partners["partners"][name]["last_sync"] = date.today().isoformat()
            save_partners_doc(partners)
            print(f"Pin advanced: {name} → {d['their_head'][:7]}")
            return
    h = d.get("their_head","?")[:7]
    print(f"# Reaction — opus sync @ {h}\n")
    print(f"Partner HEAD: {d.get('their_head','?')}")
    print("To review:")
    for r in d.get("to_review",[]): print(f"  - {r}")
    print("Reviewed (from read manifest):")
    for r in d.get("reviewed",[]): print(f"  - {r}")
    print("\nStanding Obligations:")
    for s in standing: print(f"  - {s}")
    print("\nFindings:\n[summarize here]\n")
    print("Adopt / Counter / Divergent:\n[element-by-element]\n")

def cmd_prepare_all(advance=False):
    """Combined prepare across every partner with a current per-partner draft — the interleaved
    `detect A; detect B → read → ONE combined A+B reaction → one commit` cadence. Scans the per-partner
    scratch files (no keyed schema needed); each partner gets its own section in one stub."""
    names = list(partners_doc().get("partners", {}).keys())
    drafts = [(n, jload(_draft_path(n))) for n in names if os.path.exists(_draft_path(n))]
    if not drafts:
        print("ERROR: no per-partner detect drafts — run `detect <partner>` first"); sys.exit(2)
    if advance:
        pj = partners_doc()
        for n, d in drafts:
            if n in pj.get("partners", {}) and d.get("their_head"):
                pj["partners"][n]["last_pinned"] = d["their_head"]
                pj["partners"][n]["last_sync"] = date.today().isoformat()
        save_partners_doc(pj)
        print("Pins advanced: " + ", ".join(f"{n}→{d.get('their_head','?')[:7]}" for n, d in drafts))
        return
    standing = []
    ledger = jload(ledger_path())
    if ledger.get("entries"): standing = ledger["entries"][-1].get("obligations", [])
    print(f"# Reaction — opus combined sync ({len(drafts)} partners: {', '.join(n for n, _ in drafts)})\n")
    for n, d in drafts:
        print(f"## {n} @ {d.get('their_head', '?')[:7]}")
        print("To review:")
        for r in d.get("to_review", []): print(f"  - {r}")
        print("Reviewed (from read manifest):")
        for r in d.get("reviewed", []): print(f"  - {r}")
        print()
    print("Standing Obligations:")
    for s in standing: print(f"  - {s}")
    print("\nFindings:\n[summarize across partners]\n")
    print("Adopt / Counter / Divergent:\n[element-by-element]\n")

# ── ledger (read-only summary; no schema change) ──
def cmd_ledger(recent=1, partner_filter=None):
    """A READABILITY surface over sync_ledger.json: emit a compact per-entry summary of the last
    `recent` entries. Read-only — no state mutation, no pin advance, no schema change (reads the
    ledger as-is). Schema-tolerant: the two teams' ledgers diverge (machinery), so every field is
    resolved with .get() fallbacks and obligation shapes (dict / list) are counted generically."""
    led = jload(ledger_path())
    entries = led.get("entries", [])
    top_partner = led.get("partner")
    total = len(entries)
    sel = entries
    if partner_filter:
        sel = [e for e in entries if (e.get("partner") or top_partner) == partner_filter]
    shown = sel[-recent:] if (recent and recent > 0) else sel
    def _n(x): return len(x) if isinstance(x, (list, dict)) else 0
    rows = []
    for e in shown:
        msg = e.get("their_head_msg") or e.get("our_head_msg") or ""
        row = {
            "date": e.get("date"),
            "partner": e.get("partner") or top_partner or "?",
            "head": e.get("their_head") or e.get("our_head") or "?",
            "msg": (msg[:72] + "…") if len(msg) > 72 else msg,
            "reviewed": _n(e.get("reviewed")),
            "obligations": _n(e.get("obligations")),
        }
        if "obligations_done" in e:  # team-a schema carries a done/open split; team-b's does not
            row["obligations_done"] = _n(e.get("obligations_done"))
        rows.append(row)
    print(json.dumps({"total_entries": total, "shown": len(rows), "entries": rows}, indent=2))

# ── relay (per-path, §3/I4) ──
def cmd_relay(paths=None):
    # Git operates from the repo ROOT, not home(): home() (PARALLAX_HOME) may be a
    # SUBDIRECTORY of the consumer repo (e.g. methodology/cross_team), while relayed
    # paths are repo-root-relative. A `git status -- <path>` resolved against a subdir
    # cwd silently matches nothing → falsely passes the commit-before-relay gate. Resolve
    # the toplevel so the pathspec aligns. (home() not in a repo → root falls back to
    # home(), preserving the prior non-git behavior.)
    root = repo_root()
    args = ["git","-C",root,"status","--porcelain"]
    if paths: args += ["--"] + list(paths)
    r = subprocess.run(args, capture_output=True, text=True)
    lines = [l for l in r.stdout.strip().split("\n") if l]
    if lines:
        print(f"BLOCKED — {len(lines)} uncommitted change(s):")
        for l in lines[:5]: print(f"    {l.strip()}")
        if len(lines) > 5: print(f"    ... +{len(lines)-5} more")
        print("\n  Per §3: relay requires clean path(s)."); sys.exit(1)
    h = subprocess.run(["git","-C",root,"rev-parse","--short","HEAD"], capture_output=True, text=True).stdout.strip()
    jsave(hp("_relay.json"), {"from": os.path.basename(root) or "parallax",
         "head": h, "paths": paths or []})
    print(f"OK — clean. HEAD {h}. Safe to relay.")

# ── count ──
def cmd_count(name):
    cfg, repo = partner(name)
    if cfg is None:
        print(f"ERROR: partner '{name}' not configured"); sys.exit(1)
    if not repo.is_dir():
        print(f"ERROR: partner '{name}' repo not found"); sys.exit(1)
    head = phead(repo)
    if head == "?": print(f"ERROR: cannot read partner repo"); sys.exit(1)
    last = cfg.get("last_pinned")
    pin_ok = pin_reachable(last, repo)
    n = len(git(f"log --oneline {last}..HEAD", str(repo))) if (last and pin_ok) else 0
    print(f"Partner: {name} ({cfg.get('team_name','?')})")
    print(f"  Last synced: {cfg.get('last_sync','?')} (pinned {(last or '?')[:7]})")
    print(f"  New commits since: {n}  Partner HEAD: {head[:7]}")
    if last and not pin_ok: print(f"  Status: ⚠ pin unreachable (rebase/history-rewrite?) — re-pin")
    elif n: print(f"  Status: sync recommended ({n} unread)")
    else: print(f"  Status: up to date")

# ── guard ──
def cmd_guard(target):
    target = Path(target).resolve()
    for n, p in partners_doc().get("partners",{}).items():
        rp = Path(p.get("path",""))
        base = config_root() if cross_team_config_path() else Path(home())
        if not rp.is_absolute(): rp = (base / rp).resolve()
        try:
            target.relative_to(rp)
            print(f"BLOCKED — {target} is inside partner '{n}'")
            print(f"  Use: parallax.py read {n} <path>"); sys.exit(1)
        except ValueError: pass
    print(f"OK — {target} not in any partner repo")

# ── read-guard (PreToolUse hook, --read-guard mode) ──
def cmd_read_guard():
    """PreToolUse hook — reads stdin JSON, exits 2 (blocked) if any partner
    path appears in the tool invocation outside sanctioned read mode.
    Fail-open: exits 0 on any parse error or unexpected shape."""
    sync_flag = hp(".parallax_sync_mode")
    if os.path.exists(sync_flag): sys.exit(0)  # sanctioned read in progress
    try:
        ev = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # fail-open
    tool = ev.get("tool_name","")
    ti = ev.get("tool_input",{}) or {}
    hay = " ".join(str(ti.get(k,"")) for k in ("command","file_path","path","pattern"))
    if not hay.strip(): sys.exit(0)
    try:
        paths = [p["path"] for p in partners_doc().get("partners",{}).values()]
    except Exception:
        sys.exit(0)
    for pp in paths:
        if pp and pp in hay:
            print(f"[read-guard] BLOCKED: '{tool}' touches partner repo {pp} outside sync-mode. "
                  f"Route partner reads through `parallax.py read <partner> <path>`.", file=sys.stderr)
            sys.exit(2)
    sys.exit(0)

# ── watch (rung 1) — block on a partner HEAD change, then detect+prepare; NEVER commit/relay ──
def cmd_watch(name, poll=None):
    """Block until the partner repo has work past our pin (a fresh commit, or existing
    backlog), then run the sanctioned `detect` (+ `prepare` on obligation), write `_inbox.json`,
    and exit 0 — handing the drafted cycle to the operator. The per-agent adapter re-engages on
    exit. Event-driven on the partner's local `.git/logs/HEAD` (the reflog); `--poll <secs>`
    falls back to polling where no file-watcher exists. It never commits or relays (§0)."""
    cfg, repo = partner(name)
    if cfg is None:
        print(f"ERROR: partner '{name}' not configured"); sys.exit(1)
    if not repo.is_dir():
        print(f"ERROR: partner '{name}' repo not found"); sys.exit(1)
    pinned = cfg.get("last_pinned") or ""
    reflog = repo / ".git" / "logs" / "HEAD"
    use_inotify = poll is None and bool(shutil.which("inotifywait")) and reflog.exists()
    interval = float(poll) if poll is not None else 30.0
    def pinned_still():               # True while HEAD == pin (nothing new to review)
        h = phead(repo)
        return bool(pinned) and h.startswith(pinned)
    while pinned_still():
        if use_inotify:               # wake on a reflog write, or the 1h safety timeout
            subprocess.run(["inotifywait", "-qq", "-t", "3600", "-e", "modify",
                            "-e", "close_write", str(reflog)], capture_output=True)
        else:
            time.sleep(interval)
    cmd_detect(name)                  # sanctioned: writes per-partner + legacy detect/draft
    dj = jload(_detect_path(name)) or {}   # THIS partner's record (not the shared last-run mirror)
    obligation = bool(dj.get("obligation"))
    if obligation:
        cmd_prepare(name)             # auto-draft the ledger entry + reaction stub
    inbox = {"event": "partner-head-change", "partner": name, "their_head": dj.get("their_head"),
             "obligation": obligation,
             "draft": (os.path.basename(_draft_path(name)) if obligation else None),
             "detect": os.path.basename(_detect_path(name)), "at": date.today().isoformat()}
    jsave(_inbox_path(name), inbox);  jsave(hp("_inbox.json"), inbox)   # per-partner + legacy mirror
    print(json.dumps(inbox, separators=(",", ":")))   # machine-readable summary (last line)
    # exit 0 — never commit/relay; the operator/agent owns the sweeps + the decision

# ── index-diff (rung 2) — diff partner's claims_index against last pinned copy ──
def cmd_index_diff(name):
    """Diff the partner's committed claims_index.json against the copy saved at the last
    sync pin. Emits the changed claim ids for targeted reads. Every partner read is
    manifest-logged (F2)."""
    _, repo = partner(name)
    if repo is None:
        print(f"ERROR: partner '{name}' not found"); sys.exit(1)
    head = phead(repo)
    index = _logged_gitshow(name, head, "claims_index.json", str(repo))
    if index is None:
        print(f"no claims_index.json at partner HEAD {head[:7]}")
        return
    current = json.loads(index)
    pinned = cfg.get("last_pinned") if (cfg := partner(name)[0]) else None
    if pinned and not pin_reachable(pinned, repo):   # same class as detect/count: never silently mishandle a stale pin
        print(f"⚠ pin {pinned[:7]} UNREACHABLE in {name} (rebase/history-rewrite?) — diffing against EMPTY (all claims read as 'added'); re-pin")
        pinned = None
    prev = _logged_gitshow(name, pinned, "claims_index.json", str(repo)) if pinned else None
    prev_entries = json.loads(prev).get("entries", []) if prev else []
    cur_ids = {e["id"] for e in current.get("entries", [])}
    prev_ids = {e["id"] for e in prev_entries}
    added = sorted(cur_ids - prev_ids)
    removed = sorted(prev_ids - cur_ids)
    changed = sorted(id for id in (cur_ids & prev_ids)
                     if next((e for e in current["entries"] if e["id"] == id), {})
                     != next((e for e in prev_entries if e["id"] == id), {}))
    print(json.dumps({"added": added, "removed": removed, "changed": changed}, indent=2))

# ── div-diff (rung 3) — surface divergence differences (mirrored + diffed, aging-robust) ──
def cmd_div_diff(name):
    """Diff our divergences against the partner's committed copy, computing the claim
    space over recent + archived.* on both sides (F1: aging-robust — archive state never
    reads as presence/absence). Every partner read is manifest-logged (F2)."""
    _, repo = partner(name)
    if repo is None:
        print(f"ERROR: partner '{name}' not found"); sys.exit(1)
    # Collect all claims from our side: recent + archived.*
    our_claims = {}
    for fname in ["divergences.recent.json", "divergences.archived.resolved.json",
                  "divergences.archived.open.json"]:
        fp = rp(fname)   # our divergences live at the repo ROOT, not the sync home (B6c class)
        if os.path.exists(fp):
            for e in json.load(open(fp)).get("entries", []):
                if e["claim"] not in our_claims:
                    our_claims[e["claim"]] = e
    # Collect all claims from partner's side (committed, read via logging)
    head = phead(repo)
    their_claims = {}
    their_files = {}  # claim → file name for aging_mismatch (R1)
    for fname in ["divergences.recent.json", "divergences.archived.resolved.json",
                  "divergences.archived.open.json"]:
        raw = _logged_gitshow(name, head, fname, str(repo))
        if raw:
            for e in json.loads(raw).get("entries", []):
                if e["claim"] not in their_claims:
                    their_claims[e["claim"]] = e
                    their_files[e["claim"]] = fname
    our_ids = set(our_claims)
    their_ids = set(their_claims)
    only_ours = sorted(our_ids - their_ids)
    only_theirs = sorted(their_ids - our_ids)
    disagree = []
    aging_mismatch = []
    for cid in (our_ids & their_ids):
        oe = our_claims[cid]; te = their_claims[cid]
        if oe.get("status") != te.get("status") or oe.get("crux") != te.get("crux"):
            disagree.append({"claim": cid, "ours": oe.get("status"), "theirs": te.get("status")})
        # aging mismatch: one side's entry is in a different file tier
        our_file = next((f for f in ["divergences.recent.json", "divergences.archived.resolved.json", "divergences.archived.open.json"]
                         if os.path.exists(hp(f)) and any(e["claim"] == cid for e in json.load(open(hp(f))).get("entries", []))), "unknown")
        their_file = their_files.get(cid, "unknown")
        if our_file != their_file:
            aging_mismatch.append({"claim": cid, "our_file": our_file, "their_file": their_file})
    print(json.dumps({"only_ours": only_ours, "only_theirs": only_theirs,
                      "disagree": disagree, "aging_mismatch": aging_mismatch}, indent=2))

# ── age-divergences (rung 3) — archive entries by elapsed time ──
def cmd_age_divergences():
    """Age divergence entries: resolved entries older than archive_resolved_after_days
    → archived.resolved.json. Open entries older than archive_open_after_days
    → archived.open.json. Thresholds read from divergences.recent.json aging block."""
    recent_path = rp("divergences.recent.json")   # repo root, not the sync home (B6c class)
    if not os.path.exists(recent_path):
        print("no divergences.recent.json"); return
    data = json.load(open(recent_path))
    aging = data.get("aging", {})
    resolved_days = aging.get("archive_resolved_after_days", 60)
    open_days = aging.get("archive_open_after_days", 90)
    today = date.today()
    recent = []; archived_resolved = []; archived_open = []
    for e in data.get("entries", []):
        age = (today - date.fromisoformat(e["last_updated"])).days if e.get("last_updated") else 0
        if e.get("status", "").startswith("resolved") and age >= resolved_days:
            archived_resolved.append(e)
        elif e.get("status") == "open" and age >= open_days:
            archived_open.append(e)
        else:
            recent.append(e)
    data["entries"] = recent
    json.dump(data, open(recent_path, "w"), indent=2)
    for path, entries in [("divergences.archived.resolved.json", archived_resolved),
                          ("divergences.archived.open.json", archived_open)]:
        if entries:
            existing = json.load(open(rp(path))) if os.path.exists(rp(path)) else {"entries": []}
            existing["entries"].extend(entries)
            json.dump(existing, open(rp(path), "w"), indent=2)
    print(f"aged: {len(archived_resolved)} → archived.resolved, "
          f"{len(archived_open)} → archived.open, {len(recent)} remain in recent")

# ── convergence-audit (rung 2) — flag claims that may be mis-tagged independent ──
def cmd_convergence_audit(name):
    """Flag `independent` claims in either team's claims_index that share parents,
    have suspicious commit windows, or lack measured evidence. Does NOT auto-tag —
    surfaces flags for human review. Every partner read is manifest-logged."""
    _, repo = partner(name)
    if repo is None:
        print(f"ERROR: partner '{name}' not found"); sys.exit(1)
    head = phead(repo)
    # Read our claims (repo ROOT, not sync home — same B6c class B16 caught)
    our_path = rp("claims_index.json")
    if not os.path.exists(our_path):
        our_path = hp("claims_index.json")  # fallback for home=root layout
    ours = json.load(open(our_path)) if os.path.exists(our_path) else {"entries": []}
    # Read partner's claims
    theirs_raw = _logged_gitshow(name, head, "claims_index.json", str(repo))
    theirs = json.loads(theirs_raw) if theirs_raw else {"entries": []}
    flags = []
    for e in ours.get("entries", []) + theirs.get("entries", []):
        if e.get("convergence_tag") != "independent":
            continue
        reasons = []
        if e.get("evidence_tier") not in ("measured", "inferred"):
            reasons.append("conjectural evidence cannot be independent")
        if not e.get("evidence_ref"):
            reasons.append("independent tag requires a cited measurement ref")
        if reasons:
            flags.append({"id": e["id"], "tag": "independent", "reasons": reasons})
    if flags:
        print(json.dumps({"flags": flags, "advice": "human review — do these deserve independent?"}, indent=2))
    else:
        print(json.dumps({"flags": []}, indent=2))

# ── CLI ──
if __name__ == "__main__":
    if "--read-guard" in sys.argv:
        cmd_read_guard()
    h = home()
    if h is None or (not cross_team_config_path() and not os.path.exists(os.path.join(h, "partners.json"))):
        print("ERROR: no config found — set CROSS_TEAM_CONFIG, set PARALLAX_HOME, or run from a sync home"); sys.exit(1)
    if len(sys.argv) < 2:
        print("Usage: parallax.py [detect|read|prepare|relay|count|ledger|guard|watch|index-diff|div-diff|age-divergences|convergence-audit] [args...]"); sys.exit(2)
    c = sys.argv[1]; a = sys.argv[2:]
    if c == "detect": cmd_detect(a[0] if a else default_partner())
    elif c == "read":
        if len(a) < 2: print("ERROR: read requires <partner> <path>"); sys.exit(2)
        cmd_read(a[0], a[1])
    elif c == "prepare":
        adv = "--advance" in a
        if adv: a.remove("--advance")
        if "--all" in a or (a and a[0] == "all"):   # combined stub across all partner drafts
            cmd_prepare_all(advance=adv)
        else:
            cmd_prepare(a[0] if a else default_partner(), advance=adv)
    elif c == "relay": cmd_relay(a[1:] if len(a) > 1 else None)
    elif c == "count": cmd_count(a[0] if a else default_partner())
    elif c == "ledger":
        recent = 1; pf = None
        if "--recent" in a:
            i = a.index("--recent"); recent = int(a[i + 1]) if i + 1 < len(a) else 1; a = a[:i] + a[i + 2:]
        if "--partner" in a:
            i = a.index("--partner"); pf = a[i + 1] if i + 1 < len(a) else None; a = a[:i] + a[i + 2:]
        cmd_ledger(recent=recent, partner_filter=pf)
    elif c == "guard":
        if not a: print("ERROR: guard requires <path>"); sys.exit(2)
        cmd_guard(a[0])
    elif c == "watch":
        poll = None
        if "--poll" in a:
            i = a.index("--poll"); poll = a[i + 1] if i + 1 < len(a) else "30"; a = a[:i] + a[i + 2:]
        cmd_watch(a[0] if a else default_partner(), poll=poll)
    elif c == "index-diff":
        cmd_index_diff(a[0] if a else default_partner())
    elif c == "div-diff":
        cmd_div_diff(a[0] if a else default_partner())
    elif c == "age-divergences":
        cmd_age_divergences()
    elif c == "convergence-audit":
        cmd_convergence_audit(a[0] if a else default_partner())
    else: print(f"Unknown: {c}"); sys.exit(2)
