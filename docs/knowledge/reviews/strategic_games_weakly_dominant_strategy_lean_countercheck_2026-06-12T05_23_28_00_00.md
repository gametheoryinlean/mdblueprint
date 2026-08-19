---
agent: lean-countercheck
node_id: strategic_games.weakly_dominant_strategy
created_at: "2026-06-12T05:23:28+00:00"
---

# Lean Countercheck: Weakly Dominant Strategy

## Inputs

- node file: `/home/azureuser/mdblueprint-clean/docs/knowledge/nodes/strategic_games/weakly_dominant_strategy.md`
- lean file: `/home/azureuser/EconCSLib/EconCSLib/GameTheory/StrategicGame/Dominance.lean`
- corpus root: `/home/azureuser/EconCSLib`

## Method Status

- heuristic: used

## Matched Declarations

- `StrategicGame.IsWeaklyDominant`

## Missing Declarations

- `(none)`

## Extra Declarations

- `WeaklyDominates`
- `StrictlyDominates`
- `IsStrictlyDominant`
- `StrictlyDominates.weakly`
- `IsWeaklyDominant.isBestResponse`

## Node Uses vs Extracted Dependencies

- node uses: `strategic_games.weakly_dominates`
- missing uses: (none)
- extra uses: `IsStrictlyDominant`, `IsWeaklyDominant`, `StrictlyDominates`

## Raw Snapshot

```json
{
  "corpus_root": "/home/azureuser/EconCSLib",
  "dependencies": [
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsWeaklyDominant",
      "target": "WeaklyDominates"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsStrictlyDominant",
      "target": "StrictlyDominates"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "StrictlyDominates.weakly",
      "target": "StrictlyDominates"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "StrictlyDominates.weakly",
      "target": "WeaklyDominates"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsStrictlyDominant.isWeaklyDominant",
      "target": "IsStrictlyDominant"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsStrictlyDominant.isWeaklyDominant",
      "target": "IsWeaklyDominant"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsWeaklyDominant.isBestResponse",
      "target": "IsWeaklyDominant"
    }
  ],
  "lean_file": "/home/azureuser/EconCSLib/EconCSLib/GameTheory/StrategicGame/Dominance.lean",
  "method_status": {
    "heuristic": "used"
  },
  "node": {
    "body": "# Weakly Dominant Strategy\n\nA strategy $s_i$ is weakly dominant for player $i$ if it weakly dominates every\nother strategy available to $i$:\n\n$$\\forall s'_i \\in S_i, \\quad s_i \\text{ weakly dominates } s'_i.$$",
    "file_path": "/home/azureuser/mdblueprint-clean/docs/knowledge/nodes/strategic_games/weakly_dominant_strategy.md",
    "id": "strategic_games.weakly_dominant_strategy",
    "kind": "definition",
    "lean": {
      "declarations": [
        "StrategicGame.IsWeaklyDominant"
      ],
      "modules": [
        "GameTheoryLib.StrategicGame.Dominance"
      ],
      "repository": null
    },
    "status": "admitted",
    "tags": [
      "strategic-game",
      "dominance"
    ],
    "title": "Weakly Dominant Strategy",
    "uses": [
      "strategic_games.weakly_dominates"
    ]
  },
  "source_root": "/home/azureuser/EconCSLib/EconCSLib",
  "theorems": [
    {
      "body": "def WeaklyDominates (G : StrategicGame N U) (i : N) (s s' : G.strategy i) : Prop :=\n  \u2200 \u03c3 : G.Profile, G.payoff (deviate \u03c3 i s') i \u2264 G.payoff (deviate \u03c3 i s) i\n\n/-- Strategy `s` strictly dominates strategy `s'` for player `i`. -/\n",
      "column": 1,
      "end": 1047,
      "kind": "theorem",
      "line": 29,
      "module": "GameTheory.StrategicGame.Dominance",
      "name": "WeaklyDominates",
      "source_path": "/home/azureuser/EconCSLib/EconCSLib/GameTheory/StrategicGame/Dominance.lean",
      "start": 817
    },
    {
      "body": "def StrictlyDominates (G : StrategicGame N U) (i : N) (s s' : G.strategy i) : Prop :=\n  \u2200 \u03c3 : G.Profile, G.payoff (deviate \u03c3 i s') i < G.payoff (deviate \u03c3 i s) i\n\n/-- Strategy `s` is weakly dominant for player `i`. -/\n",
      "column": 1,
      "end": 1265,
      "kind": "theorem",
      "line": 33,
      "module": "GameTheory.StrategicGame.Dominance",
      "name": "StrictlyDominates",
      "source_path": "/home/azureuser/EconCSLib/EconCSLib/GameTheory/StrategicGame/Dominance.lean",
      "start": 1047
    },
    {
      "body": "def IsWeaklyDominant (G : StrategicGame N U) (i : N) (s : G.strategy i) : Prop :=\n  \u2200 s' : G.strategy i, WeaklyDominates G i s s'\n\n/-- Strategy `s` is strictly dominant for player `i`. -/\n",
      "column": 1,
      "end": 1453,
      "kind": "theorem",
      "line": 37,
      "module": "GameTheory.StrategicGame.Dominance",
      "name": "IsWeaklyDominant",
      "source_path": "/home/azureuser/EconCSLib/EconCSLib/GameTheory/StrategicGame/Dominance.lean",
      "start": 1265
    },
    {
      "body": "def IsStrictlyDominant (G : StrategicGame N U) (i : N) (s : G.strategy i) : Prop :=\n  \u2200 s' : G.strategy i, s \u2260 s' \u2192 StrictlyDominates G i s s'\n\n/-- Strict dominance implies weak dominance. -/\n",
      "column": 1,
      "end": 1645,
      "kind": "theorem",
      "line": 41,
      "module": "GameTheory.StrategicGame.Dominance",
      "name": "IsStrictlyDominant",
      "source_path": "/home/azureuser/EconCSLib/EconCSLib/GameTheory/StrategicGame/Dominance.lean",
      "start": 1453
    },
    {
      "body": "theorem StrictlyDominates.weakly {G : StrategicGame N U} {i : N} {s s' : G.strategy i}\n    (h : StrictlyDominates G i s s') : WeaklyDominates G i s s' :=\n  fun \u03c3 => le_of_lt (h \u03c3)\n\n/-- A strictly dominant strategy is weakly dominant. -/\n",
      "column": 1,
      "end": 1882,
      "kind": "theorem",
      "line": 45,
      "module": "GameTheory.StrategicGame.Dominance",
      "name": "StrictlyDominates.weakly",
      "source_path": "/home/azureuser/EconCSLib/EconCSLib/GameTheory/StrategicGame/Dominance.lean",
      "start": 1645
    },
    {
      "body": "theorem IsStrictlyDominant.isWeaklyDominant {G : StrategicGame N U} {i : N} {s : G.strategy i}\n    [DecidableEq (G.strategy i)]\n    (h : IsStrictlyDominant G i s) : IsWeaklyDominant G i s := by\n  intro s'\n  by_cases heq : s = s'\n  \u00b7 subst heq; intro \u03c3; exact le_refl _\n  \u00b7 exact (h s' heq).weakly\n\n/-- T2: A weakly dominant strategy is a best response to any profile where player `i` plays it. -/\n",
      "column": 1,
      "end": 2279,
      "kind": "theorem",
      "line": 50,
      "module": "GameTheory.StrategicGame.Dominance",
      "name": "IsStrictlyDominant.isWeaklyDominant",
      "source_path": "/home/azureuser/EconCSLib/EconCSLib/GameTheory/StrategicGame/Dominance.lean",
      "start": 1882
    },
    {
      "body": "theorem IsWeaklyDominant.isBestResponse {G : StrategicGame N U} {i : N} {s : G.strategy i}\n    (hdom : IsWeaklyDominant G i s) (\u03c3 : G.Profile) (h\u03c3 : \u03c3 i = s) :\n    IsBestResponse G \u03c3 i := by\n  intro s'\n  have h := hdom s' \u03c3\n  simp only [\u2190 h\u03c3, Profile.deviate_self] at h\n  exact h\n",
      "column": 1,
      "end": 2559,
      "kind": "theorem",
      "line": 59,
      "module": "GameTheory.StrategicGame.Dominance",
      "name": "IsWeaklyDominant.isBestResponse",
      "source_path": "/home/azureuser/EconCSLib/EconCSLib/GameTheory/StrategicGame/Dominance.lean",
      "start": 2279
    }
  ]
}
```

## Intent

- Lean is acting as a counterchecker only.
- Blank or flawed proofs are recorded as incompleteness, not inconsistency.
- Any new lemmata discovered here are proposals for review, not automatic edits.