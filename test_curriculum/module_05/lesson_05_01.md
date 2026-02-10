# Phase Reduction Theory

## Key Insight
Oscillatory neurons near limit cycles can be reduced to a single phase variable, dramatically simplifying analysis while preserving essential synchronization dynamics—a powerful dimensionality reduction for network studies.

## Learning Objectives
- Derive phase reduction from limit cycle dynamics
- Compute phase response curves (PRCs) from full models
- Classify PRC types and relate to synchronization properties
- Apply phase reduction to network coupling analysis

## Warmup (Callback)
FHN limit cycle (lesson_01_04) is high-dimensional; phase reduction captures oscillation with single variable θ

## Content Outline
- Limit cycle oscillators: periodic solutions of ODEs
- Phase variable definition: θ ∈ [0, 2π) parameterizing cycle
- Isochrons: surfaces of constant phase in state space
- Phase response curve (PRC): Δθ vs. perturbation timing
- Type I PRC: always positive (SNIC bifurcation)
- Type II PRC: biphasic (Hopf bifurcation)
- Weak coupling assumption: perturbations small compared to limit cycle
- Phase dynamics: dθ/dt = ω + εZ(θ)I(t)

## Key Concepts
- Phase variable
- Limit cycle
- Isochron
- Phase response curve
- Type I vs. Type II PRC
- Weak coupling

## Practical Examples
- PRC computation: perturbing FHN limit cycle at different phases
- Type I PRC from SNIC model (theta neuron)
- Type II PRC from Hopf bifurcation model
- Numerical isochron calculation: backward integration
- Phase reduction validation: comparing full vs. reduced dynamics

## Verification Criteria

### Knowledge Check
Students should compute PRCs numerically, classify types, and validate phase reduction against full models

### Success Indicators
- Correctly computes PRC from limit cycle perturbations
- Classifies PRC type based on shape and bifurcation
- Validates phase reduction: reduced model matches full model
- Explains relationship between PRC type and synchronization

### Common Misconceptions
- Assuming phase reduction applies far from limit cycle
- Confusing PRC with frequency-current curve
- Neglecting weak coupling assumption violations
- Misidentifying PRC type without considering bifurcation structure
