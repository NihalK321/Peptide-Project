import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import {
  QuantumOptimizationEngine,
  ResearchDashboard,
} from './features'
import { NotFoundPage } from './pages/NotFoundPage'
import { ScalableQPULab } from './features/sequenceDesign/ScalableQPULab'
import { PeptideDesignerWorkspace } from './features/designer/PeptideDesignerWorkspace'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<ResearchDashboard />} />
          <Route path="sequence-design" element={<Navigate to="/designer" replace />} />
          <Route path="sequence-qpu" element={<ScalableQPULab />} />
          <Route path="designer" element={<PeptideDesignerWorkspace />} />
          <Route path="optimization" element={<QuantumOptimizationEngine />} />
          <Route path="404" element={<NotFoundPage />} />
          <Route path="*" element={<Navigate to="/404" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
