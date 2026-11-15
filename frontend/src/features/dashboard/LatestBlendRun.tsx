import { Link } from 'react-router-dom'
import { loadLatestBlend } from '../../services/blendResearch'
import { BlendRunResults } from '../designer/BlendRunResults'

export function LatestBlendRun() {
  const result = loadLatestBlend()
  if (!result) return <div className="rounded-lg border border-teal-200 bg-teal-50 p-4 text-sm text-teal-900">The database-backed blend researcher is ready in <Link className="font-semibold underline" to="/designer?tab=library">Peptide Designer</Link>. Set chemical targets, shortlist known sequences, and run QAOA. Legacy dashboard panels below remain demo data.</div>
  return <div className="space-y-3"><p className="text-xs text-[#607883]">Last simulation saved in this browser. Targets and source records are captured in this result; a new catalog import or target change does not recompute it.</p><BlendRunResults result={result} /><Link className="inline-block text-sm font-semibold text-teal-800 underline" to="/designer?tab=library">Configure another database-backed blend experiment</Link></div>
}
