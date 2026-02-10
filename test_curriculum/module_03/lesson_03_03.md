# Jump-Diffusion Processes: Unified Stochastic Framework

## Key Insight
Real neurons experience both continuous channel noise (diffusion) and discrete synaptic events (jumps), requiring jump-diffusion models that integrate both stochastic components for accurate predictions.

## Learning Objectives
- Formulate jump-diffusion SDEs combining Wiener and Poisson terms
- Derive Fokker-Planck equations with jump terms
- Implement hybrid numerical schemes for jump-diffusion processes
- Analyze how diffusion and jump components interact to shape firing statistics

## Warmup (Callback)
OU diffusion (lesson_03_01) + Poisson jumps (lesson_03_02) = jump-diffusion unified model

## Content Outline
- Jump-diffusion SDE: dV = f(V)dt + σdW + aεdN
- Fokker-Planck with jumps: ∂P/∂t = -∂(fP)/∂V + (σ²/2)∂²P/∂V² + λ∫[P(V-aε) - P(V)]
- Numerical integration: combining Euler-Maruyama with event-driven jumps
- Relative contributions: diffusion vs. jump variance
- Firing rate modulation: additive vs. multiplicative effects
- First-passage time problems with mixed noise
- Experimental validation: matching in vivo recordings

## Key Concepts
- Jump-diffusion process
- Fokker-Planck equation with jumps
- Hybrid numerical scheme
- Diffusion vs. jump variance
- First-passage time
- Mixed noise sources

## Practical Examples
- Jump-diffusion IF model implementation
- Variance decomposition: σ² (diffusion) vs. λa²ε² (jumps)
- Parameter regime exploration: diffusion-dominated vs. jump-dominated
- First-passage time distribution: numerical vs. analytical approximations
- Comparison with experimental intracellular recordings

## Verification Criteria

### Knowledge Check
Students should implement jump-diffusion models, decompose variance contributions, and solve first-passage time problems

### Success Indicators
- Correctly combines Euler-Maruyama with Poisson event handling
- Accurately decomposes total variance into components
- Identifies parameter regimes where jumps vs. diffusion dominate
- Computes first-passage times matching theoretical bounds

### Common Misconceptions
- Assuming diffusion and jump components are independent in their effects
- Neglecting jump contribution to variance
- Using inappropriate timesteps when jump rate is high
- Misapplying pure diffusion approximations to jump-dominated regimes
