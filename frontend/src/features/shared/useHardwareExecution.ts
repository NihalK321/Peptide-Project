import { useRef, useState } from 'react'
import { hardwareApi } from '../../services/hardware'
import type { HardwareJob, HardwareSettings, HardwareWorkflow } from '../../services/hardware'

const settingsKey = 'pepperq.hardware.settings-v1'
function stored<T>(key: string, fallback: T): T {
  try { return JSON.parse(localStorage.getItem(key) ?? 'null') as T ?? fallback } catch { return fallback }
}
function persist(key: string, value: unknown) {
  try { localStorage.setItem(key, JSON.stringify(value)) } catch { /* Recovery ID is also visible/downloadable. */ }
}

export function useHardwareExecution(page: string) {
  const [enabled, setEnabled] = useState(() => stored(`pepperq.hardware.${page}.enabled`, false))
  const [settings, setSettings] = useState<HardwareSettings>(() => stored(settingsKey, { backend_name: '', shots: 256, max_execution_seconds: 60 }))
  const [job, setJob] = useState<HardwareJob | null>(null)
  const [recoveryId, setRecoveryId] = useState(() => stored<string>(`pepperq.hardware.${page}.job`, ''))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const running = useRef(false)
  async function perform(work: () => Promise<HardwareJob>) {
    if (running.current) return
    running.current = true; setBusy(true); setError('')
    try { const response = await work(); setJob(response); return response }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Hardware request failed. Recover the run ID before another submission.'); throw reason }
    finally { running.current = false; setBusy(false) }
  }
  function keepId(id: string) { setRecoveryId(id); persist(`pepperq.hardware.${page}.job`, id) }
  return {
    enabled, settings, job, recoveryId, busy, error,
    setEnabled: (value: boolean) => { setEnabled(value); persist(`pepperq.hardware.${page}.enabled`, value) },
    setSettings: (value: HardwareSettings) => { setSettings(value); persist(settingsKey, value) },
    setRecoveryId,
    run: async (workflow: HardwareWorkflow, input: unknown) => {
      if (running.current) return
      if (!settings.backend_name.trim()) throw new Error('Enter an IBM backend name in the QPU settings first.')
      const id = crypto.randomUUID()
      keepId(id) // Save before networking, so a dropped response is recoverable.
      return perform(() => hardwareApi.run(workflow, input, settings, id))
    },
    refresh: () => perform(async () => { const response = await hardwareApi.status(recoveryId); keepId(response.request_id); return response }),
    cancel: () => perform(() => hardwareApi.cancel(recoveryId)),
  }
}

