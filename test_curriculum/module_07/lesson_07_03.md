# Frequency Control in Neuronal Models

## Key Insight
Optimal control can find synaptic inputs that drive neurons to fire at precise target frequencies, with applications to treating neurological disorders by regulating pathological firing patterns through optimized stimulation.

## Learning Objectives
- Formulate frequency control as optimal control problem
- Derive control laws for target firing rate achievement
- Analyze robustness to noise and parameter uncertainty
- Apply to neurological disorder models (epilepsy, Parkinson's)

## Warmup (Callback)
Neuronal models (module_01) with external input; optimal control designs input for desired firing

## Content Outline
- Frequency control objective: minimize |f(u) - f_target|² + α∫u²dt
- Firing rate f(u) as function of control input u
- Constraints: physiological bounds on synaptic input
- Gradient-based optimization: ∂f/∂u from adjoint methods
- Robustness analysis: sensitivity to noise and parameter variations
- Application to epilepsy: suppressing pathological synchronization
- Application to Parkinson's: regularizing basal ganglia firing
- Deep brain stimulation: optimal waveform design

## Key Concepts
- Frequency control
- Target firing rate
- Adjoint method
- Robustness
- Deep brain stimulation
- Neurological disorders

## Practical Examples
- Frequency control in IF model: analytical f-I curve inversion
- Gradient computation: adjoint method for HH model
- Optimal waveform design: periodic vs. irregular stimulation
- Robustness testing: Monte Carlo with parameter variations
- Epilepsy model: suppressing synchronization in coupled neurons

## Verification Criteria

### Knowledge Check
Students should formulate frequency control problems, compute optimal inputs, and analyze robustness

### Success Indicators
- Correctly formulates frequency control cost functional
- Computes optimal control achieving target frequency
- Implements adjoint method for gradient computation
- Demonstrates robustness to noise and parameter uncertainty

### Common Misconceptions
- Assuming linear relationship between input and firing rate
- Neglecting energy costs in control design
- Misapplying open-loop control where feedback is needed
- Ignoring physiological constraints on stimulation
