# Multi-Compartment Models: Detailed Morphology

## Key Insight
Multi-compartment models discretize complex neuronal morphology into coupled compartments, enabling simulation of realistic neurons with detailed dendritic trees while maintaining computational tractability through sparse matrix methods.

## Learning Objectives
- Discretize cable equation into compartmental ODEs
- Construct coupling matrices from morphological data
- Implement efficient numerical integration using sparse linear algebra
- Incorporate realistic channel distributions across compartments

## Warmup (Callback)
Cable equation (lesson_04_01) is continuous PDE; compartmental models discretize for complex morphologies

## Content Outline
- Compartmental approximation: spatial discretization Δx
- Coupled ODE system: C_i dV_i/dt = Σ_j G_ij(V_j - V_i) + I_ion,i + I_syn,i
- Coupling conductance: G_ij from axial resistance
- Morphology reconstruction: SWC format, NeuroMorpho.org
- Sparse matrix representation: efficient storage and computation
- Numerical integration: implicit methods for stiff systems
- Channel distribution: soma vs. dendritic vs. axonal
- Software tools: NEURON, Brian2, Arbor

## Key Concepts
- Compartmental model
- Coupling matrix
- Sparse matrix
- Morphology reconstruction
- Channel distribution
- Implicit integration

## Practical Examples
- Simple multi-compartment model: soma + dendrite + axon
- Coupling matrix construction from morphological parameters
- Sparse matrix implementation in Python (scipy.sparse)
- Realistic morphology: importing and simulating reconstructed neuron
- Channel distribution effects: comparing uniform vs. realistic distributions

## Verification Criteria

### Knowledge Check
Students should construct compartmental models from morphology, implement sparse matrix methods, and simulate realistic neurons

### Success Indicators
- Correctly discretizes cable equation into compartmental ODEs
- Constructs coupling matrix matching morphological connectivity
- Implements sparse matrix operations efficiently
- Simulates realistic neuron with imported morphology

### Common Misconceptions
- Using too coarse spatial discretization (violating Δx << λ)
- Neglecting sparse matrix methods for large morphologies
- Assuming uniform channel distribution across compartments
- Mishandling boundary conditions at branch points
