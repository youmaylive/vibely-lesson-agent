# FitzHugh-Nagumo Model: Reduced Excitable Dynamics

## Key Insight
The FitzHugh-Nagumo reduction distills the essential excitability of the Hodgkin-Huxley model into two dimensions, revealing the geometric structure of threshold, excitability, and oscillations through nullcline analysis.

## Learning Objectives
- Derive the FHN model as a reduction of HH dynamics
- Perform nullcline analysis to understand excitability and oscillations
- Classify fixed points and determine stability via linearization
- Relate FHN parameters to biological timescales and excitability properties

## Warmup (Callback)
HH model (lesson_01_03) has 4 dimensions; FHN reduces to 2D while preserving excitability

## Content Outline
- FHN equations: dv/dt = K[-v(v - α)(v - 1) - w] + I, dw/dt = b(v - cw)
- Variable interpretation: v ~ voltage, w ~ recovery (combines h, n)
- Nullcline analysis: dv/dt = 0 (cubic), dw/dt = 0 (linear)
- Fixed point location: intersection of nullclines
- Linearization and stability: Jacobian eigenvalues
- Excitability: large response to suprathreshold, small response to subthreshold
- Hopf bifurcation: transition from excitable to oscillatory regime
- Geometric interpretation: phase plane trajectories

## Key Concepts
- Nullclines
- Fixed point stability
- Excitability vs. oscillations
- Recovery variable
- Hopf bifurcation
- Phase plane analysis

## Practical Examples
- Nullcline plotting and fixed point identification
- Trajectory simulation showing excitable response to brief pulse
- Parameter variation: transition from excitable to oscillatory (vary I or b)
- Comparison with HH model: matching action potential features
- Linearization at fixed point: eigenvalue calculation for stability

## Verification Criteria

### Knowledge Check
Students should construct nullclines, classify fixed points, and demonstrate excitability vs. oscillatory regimes through parameter variation

### Success Indicators
- Accurately plots cubic v-nullcline and linear w-nullcline
- Identifies fixed point and determines stability from eigenvalues
- Demonstrates all-or-none response characteristic of excitability
- Shows transition to limit cycle oscillations via bifurcation

### Common Misconceptions
- Confusing nullclines with trajectories
- Assuming fixed point stability without eigenvalue analysis
- Neglecting the role of timescale separation (fast v, slow w)
- Misinterpreting recovery variable w as purely inhibitory
