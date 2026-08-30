"""Print the grounding-gate benchmark and injection red-team results.

    python -m scripts.eval_safety            # human-readable
    python -m scripts.eval_safety --json     # machine-readable

The numbers this prints are the ones quoted in the model card and README.
"""

from __future__ import annotations

import json
import sys

from app.llm.grounding_eval import run_benchmark
from app.llm.redteam import run_suite


def main() -> None:
    grounding = run_benchmark(n_cases=100)
    redteam = run_suite()

    if "--json" in sys.argv:
        print(json.dumps({"grounding": grounding, "redteam": redteam},
                         indent=2))
        return

    print("=" * 64)
    print("GROUNDING GATE — perturbation benchmark (100 cases)")
    print("=" * 64)
    print(f"In-scope catch rate : {grounding['in_scope_catch_rate']:.1%} "
          f"({grounding['in_scope_corruptions']} corrupted drafts)")
    print(f"False-block rate    : {grounding['false_block_rate']:.1%} "
          f"({grounding['n_clean']} clean drafts)")
    print()
    for fam, d in grounding["per_family"].items():
        tag = "" if d["in_scope"] else "  (out of scope: no new token)"
        print(f"  {fam:<20} {d['caught']:>3}/{d['n']:<3} "
              f"{d['catch_rate']:>6.1%}{tag}")

    print()
    print("=" * 64)
    print("INJECTION RED-TEAM — hostile claim_description fixtures")
    print("=" * 64)
    print(f"Attacks       : {redteam['n_attacks']}")
    print(f"Succeeded     : {redteam['n_succeeded']}")
    print(f"Attack success: {redteam['attack_success_rate']:.1%}")
    print(f"Checks        : {', '.join(redteam['checks'])}")
    print()
    for fam, d in redteam["by_family"].items():
        print(f"  {fam:<18} {d['succeeded']}/{d['n']} succeeded")
    if redteam["succeeded"]:
        print("\nFAILURES:")
        for s in redteam["succeeded"]:
            print(f"  {s['id']}: {s['failures']}")


if __name__ == "__main__":
    main()
