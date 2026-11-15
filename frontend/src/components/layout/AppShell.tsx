import { useEffect, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  Atom,
  Beaker,
  Cpu,
  Dna,
  LayoutDashboard,
  Microscope,
} from 'lucide-react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { navigationItems } from '../../app/navigation'
import { ApiClient, isApiClientError } from '../../api/client'
import { proposedEndpoints } from '../../api/endpoints'
import { StatusPill } from '../ui'
import { cn } from '../../lib/cn'

const routeIcons: Record<string, LucideIcon> = {
  '/sequence-qpu': Cpu,
  '/sequence-design': Dna,
  '/': LayoutDashboard,
  '/designer': Dna,
  '/optimization': Atom,
  '/chemistry': Beaker,
}

type ApiConnection = {
  label: string
  tone: 'blue' | 'amber' | 'slate'
}

const checkingApiConnection: ApiConnection = { label: 'API checking', tone: 'slate' }

function useApiConnection(): ApiConnection {
  const [connection, setConnection] = useState<ApiConnection>(checkingApiConnection)

  useEffect(() => {
    const controller = new AbortController()

    void new ApiClient().request<{ status?: string }>(proposedEndpoints.health, { signal: controller.signal })
      .then((response) => {
        if (!controller.signal.aborted) {
          setConnection(response.status === 'ok'
            ? { label: 'API connected', tone: 'blue' }
            : { label: 'API unavailable', tone: 'amber' })
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          const suffix = isApiClientError(error) ? ` (HTTP ${error.status})` : ''
          setConnection({ label: `API unavailable${suffix}`, tone: 'amber' })
        }
      })

    return () => controller.abort()
  }, [])

  return connection
}

function navigationClassName(isActive: boolean, compact = false): string {
  return cn(
    compact
      ? 'shrink-0 rounded-md border px-3 py-2 text-xs font-semibold transition-colors'
      : 'group flex items-start gap-3 rounded-lg border px-3 py-2.5 transition-colors',
    isActive
      ? 'border-[#B9D5EF] bg-[#EAF3FB] text-[#05635F]'
      : 'border-transparent text-[#65717D] hover:border-[#D9E0E7] hover:bg-[#EDF4FA] hover:text-[#28323C]',
  )
}

export function AppShell() {
  const location = useLocation()
  const activeItem = navigationItems.find((item) => item.to === location.pathname) ?? navigationItems[0]
  const apiConnection = useApiConnection()

  return (
    <div className="min-h-svh bg-[#F3F5F7] lg:grid lg:grid-cols-[16.5rem_minmax(0,1fr)]">
      <a
        className="sr-only fixed left-4 top-4 z-50 rounded-md bg-blue-700 px-3 py-2 text-sm font-semibold text-white focus:not-sr-only"
        href="#main-content"
      >
        Skip to content
      </a>

      <aside className="hidden border-r border-[#D9E0E7] bg-white px-4 py-5 lg:flex lg:min-h-svh lg:flex-col">
        <Brand />
        <p className="mt-7 px-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-[#81939B]">Research workspace</p>

        <nav className="mt-2 space-y-1" aria-label="Primary navigation">
          {navigationItems.map((item) => {
            const Icon = routeIcons[item.to] ?? Microscope

            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) => navigationClassName(isActive)}
              >
                <Icon className="mt-0.5 h-4 w-4 shrink-0" strokeWidth={1.8} aria-hidden="true" />
                <span className="min-w-0">
                  <span className="block text-sm font-semibold">{item.label}</span>
                  <span className="mt-0.5 block truncate text-xs text-[#7A8D96] group-hover:text-[#5E747F]">{item.description}</span>
                </span>
              </NavLink>
            )
          })}
        </nav>

        <div className="mt-auto rounded-lg border border-[#D9E0E7] bg-[#F8FAFC] p-4">
          <p className="text-xs font-semibold text-[#394957]">Research-use prototype</p>
          <p className="mt-1.5 text-xs leading-5 text-[#6B818B]">
            Interface fixtures are always labeled and are not experimental evidence or medical guidance.
          </p>
        </div>
      </aside>

      <div className="min-w-0">
        <header className="sticky top-0 z-20 border-b border-[#D9E0E7] bg-white/95 backdrop-blur">
          <div className="mx-auto flex max-w-[100rem] items-center justify-between gap-4 px-4 py-3 sm:px-6 lg:px-8">
            <div className="flex min-w-0 items-center gap-4">
              <div className="lg:hidden">
                <Brand compact />
              </div>
              <div className="hidden min-w-0 lg:block">
                <p className="text-xs font-semibold text-[#394957]">{activeItem.label}</p>
                <p className="mt-0.5 truncate text-xs text-[#7A8D96]">{activeItem.description}</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className="hidden text-xs text-[#72858E] sm:inline">USC × IBM Qiskit Fall Fest 2026</span>
              <StatusPill tone={apiConnection.tone}>{apiConnection.label}</StatusPill>
            </div>
          </div>

          <nav className="flex gap-1 overflow-x-auto border-t border-[#EDF2F4] px-3 py-2 lg:hidden" aria-label="Primary navigation">
            {navigationItems.map((item) => {
              const Icon = routeIcons[item.to] ?? Microscope

              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/'}
                  className={({ isActive }) => navigationClassName(isActive, true)}
                >
                  <span className="flex items-center gap-1.5"><Icon className="h-3.5 w-3.5" aria-hidden="true" />{item.shortLabel}</span>
                </NavLink>
              )
            })}
          </nav>
        </header>

        <main id="main-content" className="mx-auto w-full max-w-[100rem] px-4 py-7 sm:px-6 lg:px-8 lg:py-8">
          <Outlet />
        </main>

        <footer className="mx-auto flex w-full max-w-[100rem] flex-col gap-2 border-t border-[#D9E0E7] px-4 py-5 text-xs text-[#71848D] sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8">
          <span>PepperQ is a research prototype, not medical advice.</span>
          <span>Results require documented source, method, conditions, and provenance.</span>
        </footer>
      </div>
    </div>
  )
}

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <span className="grid h-9 w-9 place-items-center rounded-lg bg-[#087E78] text-xs font-bold tracking-[-0.08em] text-white shadow-sm">
        PQ
      </span>
      <span className={compact ? 'hidden sm:block' : ''}>
        <span className="block text-base font-semibold tracking-[-0.02em] text-[#28323C]">PepperQ</span>
        <span className="block text-[10px] font-medium uppercase tracking-[0.12em] text-[#6D838D]">Quantum molecular research</span>
      </span>
    </div>
  )
}
