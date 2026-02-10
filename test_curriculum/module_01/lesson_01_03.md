# Hodgkin-Huxley Model: Biophysical Foundation

## Key Insight
The Hodgkin-Huxley equations reveal how voltage-gated ion channels generate action potentials through a precise orchestration of sodium activation, sodium inactivation, and potassium activation—a mechanistic understanding that grounds all modern neuronal modeling.

## Learning Objectives
- Derive the HH equations from ionic current principles and gating kinetics
- Analyze the roles of m, h, n gating variables in action potential generation
- Implement the HH model numerically using appropriate integration methods
- Characterize action potential waveform features (threshold, peak, undershoot, duration)

## Warmup (Callback)
IF model (lesson_01_02) abstracts threshold; HH model mechanistically explains threshold through channel dynamics

## Content Outline
- Ionic current formulation: I_ion = g_ion * (V - E_ion)
- Full HH equation: C dV/dt = -g_Na m³h(V - V_Na) - g_K n⁴(V - V_K) - g_L(V - V_L) + I
- Gating variable kinetics: dn/dt = α_n(V)(1 - n) - β_n(V)n
- Voltage-dependent rate functions α(V) and β(V): empirical fits
- Sodium channel: fast activation (m³), slower inactivation (h)
- Potassium channel: delayed activation (n⁴)
- Action potential phases: depolarization, repolarization, hyperpolarization
- Numerical integration: stiff ODE considerations, adaptive timesteps

## Key Concepts
- Voltage-gated channels
- Gating variables (m, h, n)
- Activation and inactivation
- Reversal potentials (E_Na, E_K, E_L)
- Conductances (g_Na, g_K, g_L)
- Action potential waveform

## Practical Examples
- Numerical simulation of single action potential with current pulse
- Gating variable trajectories during action potential
- Ionic current decomposition: I_Na, I_K, I_L contributions
- Refractory period demonstration: response to paired pulses
- Parameter sensitivity analysis: effect of g_Na, g_K on waveform

## Verification Criteria

### Knowledge Check
Students should implement HH model producing physiological action potentials, decompose ionic currents, and explain each gating variable's role

### Success Indicators
- Generates action potentials with correct amplitude (~100 mV) and duration (~1 ms)
- Plots gating variables showing proper activation/inactivation sequences
- Explains threshold as balance between I_Na and I_K
- Demonstrates absolute and relative refractory periods

### Common Misconceptions
- Confusing activation (m, n) with inactivation (h)
- Assuming gating variables respond instantaneously to voltage changes
- Neglecting the importance of leak current in setting resting potential
- Using inappropriate numerical methods for stiff HH equations
