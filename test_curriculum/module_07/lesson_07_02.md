# Saccadic Eye Movements: Optimal Control Model

## Key Insight
Saccadic eye movements exhibit stereotyped velocity profiles that emerge naturally from variance minimization in optimal control, demonstrating how the brain solves control problems under noise to achieve precise, rapid movements.

## Learning Objectives
- Derive saccadic movement model as second-order system
- Formulate variance minimization optimal control problem
- Solve for optimal control law and resulting trajectories
- Compare model predictions with experimental saccade data

## Warmup (Callback)
Optimal control framework (lesson_07_01) applied to specific motor control problem: saccades

## Content Outline
- Saccadic dynamics: dx₁/dt = x₂, dx₂/dt = -(1/τ₁τ₂)x₁ - (1/τ₂)x₂ + (1/τ₁τ₂)u
- State variables: x₁ = position, x₂ = velocity
- Control input: u = desired position command
- Noise model: signal-dependent noise in control
- Variance minimization: minimize E[x₁²(T)] subject to dynamics
- Optimal control solution: feedback law u*(x, t)
- Main sequence: peak velocity vs. amplitude relationship
- Experimental validation: comparing with human/primate saccades

## Key Concepts
- Saccadic movement
- Variance minimization
- Signal-dependent noise
- Feedback control
- Main sequence
- Motor control

## Practical Examples
- Numerical simulation of saccadic dynamics
- Optimal control solution: Riccati equation for LQG problem
- Main sequence generation: varying target amplitude
- Noise effects: comparing deterministic vs. stochastic trajectories
- Parameter fitting: matching model to experimental data

## Verification Criteria

### Knowledge Check
Students should derive saccadic model, solve variance minimization problem, and validate against experimental data

### Success Indicators
- Correctly formulates saccadic dynamics and cost functional
- Solves for optimal control law analytically or numerically
- Generates main sequence matching experimental observations
- Explains variance minimization as computational principle

### Common Misconceptions
- Assuming saccades are purely ballistic (ignoring feedback)
- Neglecting signal-dependent noise in control
- Confusing position and velocity in state representation
- Misinterpreting main sequence as purely kinematic constraint
