# Cable Theory: Passive Signal Propagation

## Key Insight
The cable equation reveals how dendritic geometry—diameter, length, branching—fundamentally shapes synaptic integration by determining how signals attenuate and summate across space and time.

## Learning Objectives
- Derive the cable equation from first principles (Ohm's law, current conservation)
- Solve cable equation analytically for steady-state and transient cases
- Define and compute space constant λ and time constant τ
- Analyze how dendritic morphology affects synaptic integration

## Warmup (Callback)
Point models (lesson_01_02) ignore space; cable theory adds spatial dimension for realistic dendrites

## Content Outline
- Cylindrical dendrite model: axial and membrane currents
- Cable equation derivation: λ²∂²V/∂x² = τ∂V/∂t + V
- Space constant: λ = √(r_m/r_a) where r_m is membrane resistance, r_a is axial resistance
- Time constant: τ = r_m c_m
- Steady-state solution: V(x) = V₀exp(-|x|/λ)
- Transient solution: Green's function approach
- Boundary conditions: sealed end, voltage clamp, synaptic input
- Electrotonic distance: x/λ as dimensionless measure

## Key Concepts
- Cable equation
- Space constant λ
- Time constant τ
- Electrotonic distance
- Axial resistance
- Membrane resistance

## Practical Examples
- Analytical solution: voltage attenuation along passive dendrite
- Space constant calculation from morphological parameters
- Numerical solution: finite difference method for cable equation
- Synaptic input at different locations: proximal vs. distal efficacy
- Branching effects: equivalent cylinder approximation

## Verification Criteria

### Knowledge Check
Students should derive cable equation, compute λ and τ from parameters, and solve for voltage profiles analytically and numerically

### Success Indicators
- Correctly derives cable equation from current conservation
- Computes space constant matching exponential decay
- Implements finite difference scheme with proper boundary conditions
- Explains location-dependent synaptic efficacy using λ

### Common Misconceptions
- Confusing space constant with physical length
- Assuming uniform voltage along dendrite (point neuron approximation)
- Neglecting boundary conditions in analytical solutions
- Misapplying sealed-end vs. open-end boundary conditions
