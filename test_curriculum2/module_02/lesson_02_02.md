# Bifurcation Theory in Neuronal Excitability

## Key Insight
Bifurcations mark qualitative transitions in neuronal behavior—from silence to firing, from tonic to bursting—and understanding bifurcation structure reveals how neurons switch between computational modes as parameters vary.

## Learning Objectives
- Classify common bifurcations: saddle-node, Hopf, saddle-node on invariant circle
- Perform bifurcation analysis on neuronal models using continuation methods
- Relate bifurcation types to neuronal excitability classes (Type I vs. Type II)
- Predict firing onset and offset as bifurcation phenomena

## Warmup (Callback)
FHN Hopf bifurcation (lesson_01_04) introduced transition to oscillations; now systematic bifurcation classification

## Content Outline
- Bifurcation definition: qualitative change in dynamics at critical parameter
- Saddle-node bifurcation: creation/annihilation of fixed points
- Hopf bifurcation: birth of limit cycle from fixed point
- Saddle-node on invariant circle (SNIC): continuous f-I curve
- Subcritical vs. supercritical bifurcations
- Neuronal excitability classes: Type I (SNIC) vs. Type II (Hopf)
- Continuation methods: numerical tracking of equilibria and limit cycles
- Bifurcation diagrams: parameter vs. state variable plots

## Key Concepts
- Bifurcation point
- Saddle-node bifurcation
- Hopf bifurcation
- SNIC bifurcation
- Type I vs. Type II excitability
- Continuation method

## Practical Examples
- Saddle-node bifurcation in IF model: threshold appearance
- Hopf bifurcation in FHN model: parameter scan showing onset
- SNIC bifurcation in theta neuron model: arbitrarily low firing rates
- Bifurcation diagram construction for HH model with varying I
- Numerical continuation using AUTO or PyDSTool

## Verification Criteria

### Knowledge Check
Students should identify bifurcation types from phase portraits, construct bifurcation diagrams, and relate bifurcations to neuronal excitability classes

### Success Indicators
- Correctly classifies bifurcations from eigenvalue analysis
- Constructs bifurcation diagrams showing parameter-dependent transitions
- Distinguishes Type I (continuous f-I) from Type II (discontinuous f-I)
- Uses continuation software to track equilibria and limit cycles

### Common Misconceptions
- Assuming all firing onset is via Hopf bifurcation
- Confusing subcritical and supercritical bifurcations
- Neglecting hysteresis in subcritical bifurcations
- Misidentifying bifurcation type without eigenvalue calculation
