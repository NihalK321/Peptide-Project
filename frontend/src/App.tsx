import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import {
  MolecularChemistryAnalyzer,
  NoiseErrorMitigationLab,
  OptimizationTradeoffExplorer,
  PeptideDesigner,
  PeptideResultsExplorer,
  QuantumClassicalComparison,
  HeHQuantumChemistry,
  QuantumOptimizationEngine,
  ResearchDashboard,
  SequenceDesign,
} from './features'
import { NotFoundPage } from './pages/NotFoundPage'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<ResearchDashboard />} />
          <Route path="sequence-design" element={<SequenceDesign />} />
          <Route path="designer" element={<PeptideDesigner />} />
          <Route path="optimization" element={<QuantumOptimizationEngine />} />
          <Route path="quantum-chemistry" element={<HeHQuantumChemistry />} />
          <Route path="chemistry" element={<MolecularChemistryAnalyzer />} />
          <Route path="comparison" element={<QuantumClassicalComparison />} />
          <Route path="results" element={<PeptideResultsExplorer />} />
          <Route path="tradeoffs" element={<OptimizationTradeoffExplorer />} />
          <Route path="noise-lab" element={<NoiseErrorMitigationLab />} />
          <Route path="404" element={<NotFoundPage />} />
          <Route path="*" element={<Navigate to="/404" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
