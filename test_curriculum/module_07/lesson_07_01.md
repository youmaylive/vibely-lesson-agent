# Optimal Control Framework

## Key Insight
Optimal control theory provides a principled framework to find inputs that drive neuronal systems to desired states while minimizing costs, revealing computational principles underlying motor control and potential therapeutic interventions.

## Learning Objectives
- Formulate optimal control problems with state dynamics and cost functionals
- Derive necessary conditions using calculus of variations
- Understand Hamilton-Jacobi-Bellman equation as optimality condition
- Apply dynamic programming principle to neuronal control

## Warmup (Callback)
Dynamical systems (module_01) describe evolution; optimal control finds inputs steering evolution optimally

## Content Outline
- Optimal control problem: minimize J = ∫ L(x, u, t)dt subject to dx/dt = f(x, u, t)
- Cost functional: terminal cost + running cost
- Control constraints: bounded inputs, energy penalties
- Calculus of variations: Euler-Lagrange equations
- Hamiltonian formulation: H(x, p, u) = L(x, u) + p·f(x, u)
- Hamilton-Jacobi-Bellman equation: -∂V/∂t = min_u[L(x,u) + ∂V/∂x·f(x,u)]
- Dynamic programming: principle of optimality
- Numerical methods: shooting, collocation, direct transcription

## Key Concepts
- Cost functional
- Hamiltonian
- Hamilton-Jacobi-Bellman equation
- Dynamic programming
- Calculus of variations
- Optimal control

## Practical Examples
- Linear-quadratic regulator (LQR): analytical solution
- Minimum time control: bang-bang solutions
- Energy-optimal control: smooth trajectories
- Numerical solution: direct transcription with optimization
- Neuronal application: driving IF neuron to target firing rate

## Verification Criteria

### Knowledge Check
Students should formulate optimal control problems, derive optimality conditions, and solve numerically

### Success Indicators
- Correctly formulates cost functional and dynamics
- Derives Euler-Lagrange or HJB equations
- Implements numerical optimal control solver
- Validates solutions satisfy necessary conditions

### Common Misconceptions
- Confusing necessary and sufficient conditions for optimality
- Assuming HJB equation is always solvable analytically
- Neglecting control constraints in formulation
- Misapplying linear methods to nonlinear problems
