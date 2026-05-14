import GameTheoryLib.StrategicGame.Basic

namespace StrategicGame

variable {ι U : Type*}

def IsBestResponse (G : StrategicGame ι U) [Preorder U] [DecidableEq ι]
    (σ : G.Profile) (i : ι) : Prop :=
  ∀ s' : G.strategy i, G.payoff (deviate σ i s') i ≤ G.payoff σ i

def IsNashEquilibrium (G : StrategicGame ι U) [Preorder U] [DecidableEq ι]
    (σ : G.Profile) : Prop :=
  ∀ i : ι, IsBestResponse G σ i

theorem IsNashEquilibrium.of_dominant : True := sorry

end StrategicGame
