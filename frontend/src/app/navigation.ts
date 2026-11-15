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
    to: '/',
    label: 'Research Dashboard',
    shortLabel: 'Dashboard',
    description: 'Experiment readiness and active studies',
  },
  {
    to: '/designer',
    label: 'Peptide Designer',
    shortLabel: 'Designer',
    description: 'Design sequences or browse known peptides',
  },
  {
    to: '/optimization',
    label: 'Blend Optimization',
    shortLabel: 'Optimization',
    description: 'QAOA subset-selection workspace',
  },
]
