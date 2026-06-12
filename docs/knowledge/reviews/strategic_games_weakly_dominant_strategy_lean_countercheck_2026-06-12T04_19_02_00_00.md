---
agent: lean-countercheck
node_id: strategic_games.weakly_dominant_strategy
created_at: "2026-06-12T04:19:02+00:00"
---

# Lean Countercheck: Weakly Dominant Strategy

## Inputs

- node file: `/home/azureuser/mdblueprint-clean/docs/knowledge/nodes/strategic_games/weakly_dominant_strategy.md`
- lean file: `/home/azureuser/EconCSLib/EconCSLib/GameTheory/StrategicGame/Dominance.lean`
- corpus root: `/home/azureuser/EconCSLib`

## Method Status

- heuristic: used
- lean-lsp-mcp: available: uvx lean-lsp-mcp --help succeeded

## Matched Declarations

- `StrategicGame.IsWeaklyDominant`

## Missing Declarations

- `(none)`

## Extra Declarations

- `WeaklyDominates`
- `StrictlyDominates`
- `IsWeaklyDominant`
- `IsStrictlyDominant`
- `StrictlyDominates.weakly`
- `IsStrictlyDominant.isWeaklyDominant`
- `IsWeaklyDominant.isBestResponse`

## Node Uses vs Extracted Dependencies

- node uses: `strategic_games.weakly_dominates`
- missing uses: `strategic_games.weakly_dominates`
- extra uses: `A`, `G`, `IsBestResponse`, `IsStrictlyDominant`, `IsWeaklyDominant`, `N`, `Profile`, `Strategy`, `StrictlyDominates`, `T2`, `U`, `WeaklyDominates`, `a`, `any`, `at`, `by_cases`, `deviate`, `deviate_self`, `exact`, `for`, `h`, `hσ`, `i`, `intro`, `is`, `le_of_lt`, `le_refl`, `payoff`, `s`, `simp`, `subst`, `to`

## Raw Snapshot

```json
{
  "corpus_root": "/home/azureuser/EconCSLib",
  "dependencies": [
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "WeaklyDominates",
      "target": "Strategy"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "WeaklyDominates",
      "target": "Profile"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "WeaklyDominates",
      "target": "deviate"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "WeaklyDominates",
      "target": "payoff"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "WeaklyDominates",
      "target": "for"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "WeaklyDominates",
      "target": "G"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "WeaklyDominates",
      "target": "N"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "WeaklyDominates",
      "target": "U"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "WeaklyDominates",
      "target": "i"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "WeaklyDominates",
      "target": "s"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "StrictlyDominates",
      "target": "Strategy"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "StrictlyDominates",
      "target": "Profile"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "StrictlyDominates",
      "target": "deviate"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "StrictlyDominates",
      "target": "payoff"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "StrictlyDominates",
      "target": "for"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "StrictlyDominates",
      "target": "is"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "StrictlyDominates",
      "target": "G"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "StrictlyDominates",
      "target": "N"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "StrictlyDominates",
      "target": "U"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "StrictlyDominates",
      "target": "i"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "StrictlyDominates",
      "target": "s"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsWeaklyDominant",
      "target": "WeaklyDominates"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsWeaklyDominant",
      "target": "Strategy"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsWeaklyDominant",
      "target": "for"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsWeaklyDominant",
      "target": "is"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsWeaklyDominant",
      "target": "G"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsWeaklyDominant",
      "target": "N"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsWeaklyDominant",
      "target": "U"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsWeaklyDominant",
      "target": "i"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsWeaklyDominant",
      "target": "s"
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
      "source": "IsStrictlyDominant",
      "target": "G"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsStrictlyDominant",
      "target": "N"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsStrictlyDominant",
      "target": "U"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsStrictlyDominant",
      "target": "i"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsStrictlyDominant",
      "target": "s"
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
      "source": "StrictlyDominates.weakly",
      "target": "le_of_lt"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "StrictlyDominates.weakly",
      "target": "is"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "StrictlyDominates.weakly",
      "target": "A"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "StrictlyDominates.weakly",
      "target": "G"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "StrictlyDominates.weakly",
      "target": "N"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "StrictlyDominates.weakly",
      "target": "U"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "StrictlyDominates.weakly",
      "target": "h"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "StrictlyDominates.weakly",
      "target": "i"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "StrictlyDominates.weakly",
      "target": "s"
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
      "source": "IsStrictlyDominant.isWeaklyDominant",
      "target": "by_cases"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsStrictlyDominant.isWeaklyDominant",
      "target": "le_refl"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsStrictlyDominant.isWeaklyDominant",
      "target": "exact"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsStrictlyDominant.isWeaklyDominant",
      "target": "intro"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsStrictlyDominant.isWeaklyDominant",
      "target": "subst"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsStrictlyDominant.isWeaklyDominant",
      "target": "any"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsStrictlyDominant.isWeaklyDominant",
      "target": "T2"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsStrictlyDominant.isWeaklyDominant",
      "target": "is"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsStrictlyDominant.isWeaklyDominant",
      "target": "to"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsStrictlyDominant.isWeaklyDominant",
      "target": "A"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsStrictlyDominant.isWeaklyDominant",
      "target": "G"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsStrictlyDominant.isWeaklyDominant",
      "target": "N"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsStrictlyDominant.isWeaklyDominant",
      "target": "U"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsStrictlyDominant.isWeaklyDominant",
      "target": "a"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsStrictlyDominant.isWeaklyDominant",
      "target": "h"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsStrictlyDominant.isWeaklyDominant",
      "target": "i"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsStrictlyDominant.isWeaklyDominant",
      "target": "s"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsWeaklyDominant.isBestResponse",
      "target": "IsWeaklyDominant"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsWeaklyDominant.isBestResponse",
      "target": "IsBestResponse"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsWeaklyDominant.isBestResponse",
      "target": "deviate_self"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsWeaklyDominant.isBestResponse",
      "target": "Profile"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsWeaklyDominant.isBestResponse",
      "target": "exact"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsWeaklyDominant.isBestResponse",
      "target": "intro"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsWeaklyDominant.isBestResponse",
      "target": "simp"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsWeaklyDominant.isBestResponse",
      "target": "at"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsWeaklyDominant.isBestResponse",
      "target": "h\u03c3"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsWeaklyDominant.isBestResponse",
      "target": "G"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsWeaklyDominant.isBestResponse",
      "target": "N"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsWeaklyDominant.isBestResponse",
      "target": "U"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsWeaklyDominant.isBestResponse",
      "target": "h"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsWeaklyDominant.isBestResponse",
      "target": "i"
    },
    {
      "kind": "hard",
      "module": "GameTheory.StrategicGame.Dominance",
      "source": "IsWeaklyDominant.isBestResponse",
      "target": "s"
    }
  ],
  "lean_file": "/home/azureuser/EconCSLib/EconCSLib/GameTheory/StrategicGame/Dominance.lean",
  "method_status": {
    "heuristic": "used",
    "lean-lsp-mcp": "available: uvx lean-lsp-mcp --help succeeded"
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
      "end": 1047,
      "kind": "theorem",
      "module": "GameTheory.StrategicGame.Dominance",
      "name": "WeaklyDominates",
      "source_path": "/home/azureuser/EconCSLib/EconCSLib/GameTheory/StrategicGame/Dominance.lean",
      "start": 817
    },
    {
      "body": "def StrictlyDominates (G : StrategicGame N U) (i : N) (s s' : G.strategy i) : Prop :=\n  \u2200 \u03c3 : G.Profile, G.payoff (deviate \u03c3 i s') i < G.payoff (deviate \u03c3 i s) i\n\n/-- Strategy `s` is weakly dominant for player `i`. -/\n",
      "end": 1265,
      "kind": "theorem",
      "module": "GameTheory.StrategicGame.Dominance",
      "name": "StrictlyDominates",
      "source_path": "/home/azureuser/EconCSLib/EconCSLib/GameTheory/StrategicGame/Dominance.lean",
      "start": 1047
    },
    {
      "body": "def IsWeaklyDominant (G : StrategicGame N U) (i : N) (s : G.strategy i) : Prop :=\n  \u2200 s' : G.strategy i, WeaklyDominates G i s s'\n\n/-- Strategy `s` is strictly dominant for player `i`. -/\n",
      "end": 1453,
      "kind": "theorem",
      "module": "GameTheory.StrategicGame.Dominance",
      "name": "IsWeaklyDominant",
      "source_path": "/home/azureuser/EconCSLib/EconCSLib/GameTheory/StrategicGame/Dominance.lean",
      "start": 1265
    },
    {
      "body": "def IsStrictlyDominant (G : StrategicGame N U) (i : N) (s : G.strategy i) : Prop :=\n  \u2200 s' : G.strategy i, s \u2260 s' \u2192 StrictlyDominates G i s s'\n\n/-- Strict dominance implies weak dominance. -/\n",
      "end": 1645,
      "kind": "theorem",
      "module": "GameTheory.StrategicGame.Dominance",
      "name": "IsStrictlyDominant",
      "source_path": "/home/azureuser/EconCSLib/EconCSLib/GameTheory/StrategicGame/Dominance.lean",
      "start": 1453
    },
    {
      "body": "theorem StrictlyDominates.weakly {G : StrategicGame N U} {i : N} {s s' : G.strategy i}\n    (h : StrictlyDominates G i s s') : WeaklyDominates G i s s' :=\n  fun \u03c3 => le_of_lt (h \u03c3)\n\n/-- A strictly dominant strategy is weakly dominant. -/\n",
      "end": 1882,
      "kind": "theorem",
      "module": "GameTheory.StrategicGame.Dominance",
      "name": "StrictlyDominates.weakly",
      "source_path": "/home/azureuser/EconCSLib/EconCSLib/GameTheory/StrategicGame/Dominance.lean",
      "start": 1645
    },
    {
      "body": "theorem IsStrictlyDominant.isWeaklyDominant {G : StrategicGame N U} {i : N} {s : G.strategy i}\n    [DecidableEq (G.strategy i)]\n    (h : IsStrictlyDominant G i s) : IsWeaklyDominant G i s := by\n  intro s'\n  by_cases heq : s = s'\n  \u00b7 subst heq; intro \u03c3; exact le_refl _\n  \u00b7 exact (h s' heq).weakly\n\n/-- T2: A weakly dominant strategy is a best response to any profile where player `i` plays it. -/\n",
      "end": 2279,
      "kind": "theorem",
      "module": "GameTheory.StrategicGame.Dominance",
      "name": "IsStrictlyDominant.isWeaklyDominant",
      "source_path": "/home/azureuser/EconCSLib/EconCSLib/GameTheory/StrategicGame/Dominance.lean",
      "start": 1882
    },
    {
      "body": "theorem IsWeaklyDominant.isBestResponse {G : StrategicGame N U} {i : N} {s : G.strategy i}\n    (hdom : IsWeaklyDominant G i s) (\u03c3 : G.Profile) (h\u03c3 : \u03c3 i = s) :\n    IsBestResponse G \u03c3 i := by\n  intro s'\n  have h := hdom s' \u03c3\n  simp only [\u2190 h\u03c3, Profile.deviate_self] at h\n  exact h\n",
      "end": 2559,
      "kind": "theorem",
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