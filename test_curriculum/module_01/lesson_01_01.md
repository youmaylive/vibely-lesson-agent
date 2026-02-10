# Dynamical Systems Framework for Neuroscience

## Key Insight
Neuronal behavior can be precisely characterized as trajectories in state space, where understanding attractors and basins reveals how neurons respond to stimuli and return to rest.

## Learning Objectives
- Define dynamical systems in the context of neuronal modeling
- Distinguish between deterministic and stochastic dynamical systems
- Identify fixed point attractors and their attractive basins in neuronal models
- Relate mathematical concepts to biological phenomena (resting potential, firing patterns)

## Content Outline
- Mathematical definition of dynamical systems: dx/dt = f(x, t)
- State space representation and trajectories
- Deterministic vs. stochastic systems: when noise matters
- Attractors: fixed points, limit cycles, and strange attractors
- Attractive basins and initial condition sensitivity
- Biological interpretation: resting potential as fixed point attractor
- Phase portraits and geometric analysis

## Key Concepts
- State space
- Trajectory
- Attractor
- Fixed point
- Attractive basin
- Deterministic vs. stochastic dynamics

## Practical Examples
- 1D linear system: dV/dt = -(V - V_rest)/τ with analytical solution
- Geometric analysis of resting potential as stable fixed point
- Numerical simulation of trajectories from different initial conditions
- Phase portrait construction for 2D neuronal models

## Verification Criteria

### Knowledge Check
Students should derive equilibrium points analytically, classify stability, and simulate trajectories converging to attractors

### Success Indicators
- Correctly identifies fixed points from differential equations
- Sketches accurate phase portraits showing flow directions
- Explains biological meaning of attractors in neuronal context
- Implements numerical integration to verify analytical predictions

### Common Misconceptions
- Confusing equilibrium points with attractors (not all equilibria are attracting)
- Assuming all neuronal models have unique attractors
- Neglecting the role of initial conditions in determining long-term behavior
