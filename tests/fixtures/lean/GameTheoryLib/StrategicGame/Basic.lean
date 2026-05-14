import Mathlib.Logic.Function.Basic

structure StrategicGame (ι : Type*) (U : Type*) where
  strategy : ι → Type*
  payoff : (∀ i, strategy i) → ι → U

namespace StrategicGame

variable {ι U : Type*}

abbrev Profile (G : StrategicGame ι U) := ∀ i, G.strategy i

abbrev deviate {G : StrategicGame ι U} [DecidableEq ι]
    (σ : G.Profile) (i : ι) (s' : G.strategy i) : G.Profile :=
  Function.update σ i s'

end StrategicGame
