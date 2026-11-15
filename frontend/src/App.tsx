import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import {
  MolecularChemistryAnalyzer,
  PeptideDesigner,
  QuantumOptimizationEngine,
  ResearchDashboard,
  SequenceDesign,
} from './features'
import { NotFoundPage } from './pages/NotFoundPage'
import { ScalableQPULab } from './features/sequenceDesign/ScalableQPULab'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<ResearchDashboard />} />
          <Route path="sequence-design" element={<SequenceDesign />} />
          <Route path="sequence-qpu" element={<ScalableQPULab />} />
          <Route path="designer" element={<PeptideDesigner />} />
          <Route path="optimization" element={<QuantumOptimizationEngine />} />
          <Route path="chemistry" element={<MolecularChemistryAnalyzer />} />
          <Route path="404" element={<NotFoundPage />} />
          <Route path="*" element={<Navigate to="/404" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
