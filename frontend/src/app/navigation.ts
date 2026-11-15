export type NavigationItem = {
  to: string
  label: string
  shortLabel: string
  description: string
}

export const navigationItems: NavigationItem[] = [
  {
    to: '/sequence-qpu',
    label: 'Scalable QPU Lab',
    shortLabel: 'QPU Lab',
    description: 'Large sequence costs and IBM hardware',
  },
  {
    to: '/sequence-design',
    label: 'Sequence Design',
    shortLabel: 'Sequence Design',
    description: 'Design residue choices with QAOA',
  },
  {
    to: '/',
    label: 'Research Dashboard',
    shortLabel: 'Dashboard',
    description: 'Experiment readiness and active studies',
  },
  {
    to: '/designer',
    label: 'Peptide Designer',
    shortLabel: 'Designer',
    description: 'Candidate pools and sequence variants',
  },
  {
    to: '/optimization',
    label: 'Blend Optimization',
    shortLabel: 'Optimization',
    description: 'QAOA subset-selection workspace',
  },
  {
    to: '/quantum-chemistry',
    label: 'Quantum Chemistry',
    shortLabel: 'HeH+ VQE',
    description: 'HeH+ potential-energy study',
  },
  {
    to: '/chemistry',
    label: 'Molecular Analysis',
    shortLabel: 'Chemistry',
    description: 'Descriptors, proxies, and structures',
  },
  {
    to: '/comparison',
    label: 'Quantum vs Classical',
    shortLabel: 'Comparison',
    description: 'Fair baseline comparison',
  },
  {
    to: '/results',
    label: 'Blend Results',
    shortLabel: 'Results',
    description: 'Rankings, terms, and provenance',
  },
  {
    to: '/tradeoffs',
    label: 'Trade-Off Explorer',
    shortLabel: 'Trade-offs',
    description: 'Objective-frontier exploration',
  },
  {
    to: '/noise-lab',
    label: 'Noise Study',
    shortLabel: 'Noise Lab',
    description: 'Optional error-mitigation analysis',
  },
]
