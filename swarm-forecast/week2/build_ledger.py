"""
Build the week-2 Swarm Forecast ledger and summary from the raw answer files.

Labels were assigned by hand (anthropic orchestrator, 2026-09-14) against taxonomy v1,
one primary label per line. Boundary rule used for A vs B, checked against the week-1
ledger before labeling: a signature-gated service sold to other agents is B; the same
service sold to the market (people, firms) is A. Trust, reputation and distribution moves,
with or without spend, are G. Cap-scheduling and entity-as-operating-step lines are F.
Run: python build_ledger.py   (from this folder)
"""

import glob
import hashlib
import io
import json
import os
import re
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DATE = "2026-09-14"
PROMPT = io.open(os.path.join(HERE, "..", "prompt.txt"), encoding="utf-8").read().strip()
TAXONOMY = json.load(io.open(os.path.join(HERE, "..", "claude-2026-09-09.json"), encoding="utf-8"))["taxonomy"]
TIERS = {"haiku": "claude-haiku-4-5", "sonnet": "claude-sonnet-5", "opus": "claude-opus-5"}

LABELS = {
    "haiku-01": "BAB", "haiku-02": "BBB", "haiku-03": "AGF", "haiku-04": "IBE", "haiku-05": "BAB",
    "haiku-06": "BBB", "haiku-07": "AAA", "haiku-08": "BBD", "haiku-09": "DDD", "haiku-10": "DFH",
    "sonnet-01": "DFG", "sonnet-02": "DFG", "sonnet-03": "AGF", "sonnet-04": "AFG", "sonnet-05": "AFG",
    "sonnet-06": "AFG", "sonnet-07": "AGF", "sonnet-08": "DGF", "sonnet-09": "IAI", "sonnet-10": "BBC",
    "opus-01": "ABE", "opus-02": "ACB", "opus-03": "ACB", "opus-04": "ACB", "opus-05": "BCE",
    "opus-06": "ACB", "opus-07": "BCB", "opus-08": "ACB", "opus-09": "CAE", "opus-10": "BCB",
}
# lines asserting a credential (attorney, notary, licensed) the prompt never gave
CREDENTIAL_FLAGS = {("haiku-06", 3), ("opus-10", 3)}
BUSINESS = set("ABCDEHI")   # F and G are operating tactics


def strategy_lines(text):
    """First three numbered items; continuation lines (indented or unnumbered) are joined."""
    out, cur = [], None
    for raw in text.splitlines():
        line = raw.rstrip()
        m = re.match(r"^\s*(?:\*\*)?([123])[.)]\s*(?:\*\*)?(.*)$", line)
        expected = len(out) + (2 if cur is not None else 1)
        if m and int(m.group(1)) == expected:
            if cur is not None:
                out.append(cur)
                if len(out) == 3:
                    cur = None
                    break
            cur = m.group(2).strip()
            continue
        if cur is not None:
            if line.strip() == "" or re.match(r"^[A-Z][A-Z /]+$", line.strip()) or line.strip().startswith(("---", "Core insight", "WHY", "Reason", "STANDING", "TIEBREAKER", "WHAT")):
                out.append(cur); cur = None
                if len(out) == 3:
                    break
                continue
            cur += " " + line.strip()
    if cur is not None and len(out) < 3:
        out.append(cur)
    if not out:
        # unnumbered answers (haiku-01): the first three substantive paragraphs
        paras = [" ".join(p.split()) for p in re.split(r"\n\s*\n", text)]
        out = [p for p in paras if len(p) > 60 and not p.lower().startswith(("top 3", "core insight", "---"))]
    return [re.sub(r"\*\*", "", s).strip() for s in out[:3]]


def main():
    ledger = []
    counts = {t: Counter() for t in TIERS}
    mention = defaultdict(lambda: Counter())
    flags = Counter()
    for f in sorted(glob.glob(os.path.join(HERE, "*.txt"))):
        sid = os.path.basename(f)[:-4]
        if sid not in LABELS:
            continue
        tier = sid.split("-")[0]
        raw = io.open(f, encoding="utf-8").read()
        sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        lines = strategy_lines(raw)
        assert len(lines) == 3, (sid, len(lines))
        labs = LABELS[sid]
        seen = set()
        for i, (text, lab) in enumerate(zip(lines, labs), start=1):
            flag = (sid, i) in CREDENTIAL_FLAGS
            counts[tier][lab] += 1
            flags[tier] += int(flag)
            seen.add(lab)
            ledger.append({
                "sample_id": sid, "tier": tier, "model_reported": TIERS[tier], "strategy_number": i,
                "text": text, "raw_file": "swarm-forecast/week2/{}.txt".format(sid), "raw_sha256": sha,
                "label": lab, "label_kind": "business" if lab in BUSINESS else "tactic",
                "unsupported_credential_flag": flag,
                "context_isolation": "fresh Agent-tool subagent per sample, reported by the runner, not verifiable from the answer file",
                "labeled_by": "anthropic orchestrator, by hand, 2026-09-14", "taxonomy_version": "v1",
            })
        for lab in seen:
            mention[lab][tier] += 1
    with io.open(os.path.join(HERE, "ledger-{}.jsonl".format(DATE)), "w", encoding="utf-8", newline="\n") as out:
        for r in ledger:
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
    total = Counter()
    for t in counts:
        total.update(counts[t])
    wk1 = json.load(io.open(os.path.join(HERE, "..", "claude-2026-09-09.json"), encoding="utf-8"))
    summary = {
        "series": "swarm_forecast", "lineage": "anthropic", "date": DATE, "sample": "week 2 (weekly resample; not a release-day sample)",
        "prompt": PROMPT, "method": "Fresh-context Agent-tool subagent per sample, model alias per tier, no tools except writing the answer to a file; 10 samples per tier, 3 strategy lines each = 90 lines. Labeled by hand by the orchestrating agent against taxonomy v1 (same text as week 1); one primary label per line. Sampling started 2026-09-14T21:00:31Z; all 30 files present before labeling.",
        "tiers": TIERS, "taxonomy": TAXONOMY,
        "counts_by_tier": {t: {k: counts[t].get(k, 0) for k in "ABCDEFGHI"} for t in TIERS},
        "counts_total": {**{k: total.get(k, 0) for k in "ABCDEFGHI"}, "n_lines": sum(total.values())},
        "week1_counts_total": wk1["counts_total"], "week1_counts_by_tier": wk1["counts_by_tier"],
        "samples_mentioning_by_tier": {"signature_A": dict(mention["A"]), "sell_to_swarm_B": dict(mention["B"]), "buy_cash_flow_C": dict(mention["C"]), "dataset_E": dict(mention["E"])},
        "unsupported_credential_flag_lines_by_tier": dict(flags),
        "labeling_rule_note": "A vs B boundary: buyer is other agents -> B; buyer is the market -> A. Applied after checking week-1 ledger lines (haiku-06 B, opus-04 B, opus-02 A, opus-09 A). Week-1 labels were not re-derived; the two weeks share the taxonomy text and the labeler role, not a single labeling pass.",
        "caveats": ["Model aliases (haiku, sonnet, opus) resolve to whatever version the runner serves on the day; the answer files do not record a version string, so a version change between weeks cannot be excluded from the files alone.",
                    "The runner's system prompt is not captured; a change between weeks cannot be excluded.",
                    "n=10 answers per tier; three lines from one answer are correlated. Read tier-level shifts of a few lines as noise."],
        "ledger": "swarm-forecast/week2/ledger-{}.jsonl".format(DATE),
    }
    io.open(os.path.join(HERE, "claude-{}.json".format(DATE)), "w", encoding="utf-8", newline="\n").write(json.dumps(summary, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(summary["counts_by_tier"], indent=1))
    print("total", summary["counts_total"])
    print("mention", json.dumps(summary["samples_mentioning_by_tier"]))
    print("flags", dict(flags))


if __name__ == "__main__":
    main()
