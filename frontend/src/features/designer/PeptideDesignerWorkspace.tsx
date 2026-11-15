import { useRef } from 'react'
import type { KeyboardEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { SectionHeading } from '../../components/ui'
import type { BlendCandidate } from '../../services/blendResearch'
import { SequenceDesign } from '../sequenceDesign/SequenceDesign'
import type { SequenceDesignHandle } from '../sequenceDesign/SequenceDesign'
import { PeptideDesigner } from './PeptideDesigner'

export function PeptideDesignerWorkspace() {
  const [params, setParams] = useSearchParams()
  const libraryActive = params.get('tab') === 'library'
  const sequenceEditor = useRef<SequenceDesignHandle>(null)
  const sequenceTab = useRef<HTMLButtonElement>(null)
  const libraryTab = useRef<HTMLButtonElement>(null)

  function selectTab(library: boolean, focus = false) {
    setParams((previous) => {
      const next = new URLSearchParams(previous)
      if (library) next.set('tab', 'library')
      else next.delete('tab')
      return next
    })
    if (focus) (library ? libraryTab : sequenceTab).current?.focus()
  }
  function tabKey(event: KeyboardEvent<HTMLButtonElement>) {
    if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
      event.preventDefault()
      selectTab(event.key === 'End' || (event.key !== 'Home' && !libraryActive), true)
    }
  }
  function useTemplate(candidate: BlendCandidate) {
    sequenceEditor.current?.loadTemplate(candidate)
    selectTab(false)
    sequenceTab.current?.focus()
  }
  return <div className="space-y-5">
    <SectionHeading eyebrow="Peptide research workspace" title="Peptide Designer" description="Design a sequence from scratch or start from a known peptide. Choose editable positions and chemical goals, then optimize and inspect the results." />
    <div role="tablist" aria-label="Peptide Designer modes" className="flex flex-wrap gap-2 border-b border-slate-200 pb-3">
      <button type="button" role="tab" id="designer-sequence-tab" aria-controls="designer-sequence-panel" aria-selected={!libraryActive} tabIndex={libraryActive ? -1 : 0} ref={sequenceTab} onKeyDown={tabKey} onClick={() => selectTab(false)} className={`rounded-lg border px-4 py-2 text-sm font-semibold ${libraryActive ? 'border-slate-200 bg-white text-slate-600' : 'border-blue-200 bg-blue-50 text-blue-900'}`}>Design a Sequence</button>
      <button type="button" role="tab" id="designer-library-tab" aria-controls="designer-library-panel" aria-selected={libraryActive} tabIndex={libraryActive ? 0 : -1} ref={libraryTab} onKeyDown={tabKey} onClick={() => selectTab(true)} className={`rounded-lg border px-4 py-2 text-sm font-semibold ${libraryActive ? 'border-blue-200 bg-blue-50 text-blue-900' : 'border-slate-200 bg-white text-slate-600'}`}>Browse Known Peptides</button>
    </div>
    <section role="tabpanel" id="designer-sequence-panel" aria-labelledby="designer-sequence-tab" hidden={libraryActive}>
      <SequenceDesign embedded editorRef={sequenceEditor} />
    </section>
    <section role="tabpanel" id="designer-library-panel" aria-labelledby="designer-library-tab" hidden={!libraryActive}>
      <PeptideDesigner embedded onUseTemplate={useTemplate} />
    </section>
  </div>
}
