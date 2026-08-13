import { useEffect, useState } from 'react'

import { getHealth } from '../api/client'
import { BackendStatus } from '../components/BackendStatus'
import type { ConnectionState } from '../types/health'

const traceSteps = ['Review', 'Finding', 'Requirement', 'TestCase']

export function HomePage() {
  const [connection, setConnection] = useState<ConnectionState>({ status: 'checking' })

  useEffect(() => {
    const controller = new AbortController()

    getHealth(controller.signal)
      .then((health) => setConnection({ status: 'connected', health }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') {
          return
        }

        setConnection({
          status: 'failed',
          message: error instanceof Error ? error.message : 'The backend health check failed.',
        })
      })

    return () => controller.abort()
  }, [])

  return (
    <main className="min-h-screen overflow-hidden bg-[#f4f8fc] px-5 py-6 text-[#132a46] sm:px-8 sm:py-8 lg:px-12">
      <div className="mx-auto flex min-h-[calc(100vh-3rem)] max-w-[1180px] flex-col rounded-[2rem] border border-white/80 bg-white/80 shadow-[0_30px_100px_rgba(45,81,122,0.12)] backdrop-blur-sm sm:min-h-[calc(100vh-4rem)]">
        <header className="flex items-center justify-between border-b border-[#dce7f1] px-6 py-5 sm:px-10">
          <div className="flex items-center gap-3">
            <span className="grid size-9 place-items-center rounded-full bg-[#175bd8] font-mono text-xs font-bold text-white">AR</span>
            <span className="text-sm font-semibold tracking-[-0.01em]">App Review Insights</span>
          </div>
          <span className="rounded-full border border-[#d7e3ee] px-3 py-1 font-mono text-[0.68rem] uppercase tracking-[0.14em] text-[#65778d]">
            Phase 1 · Shell
          </span>
        </header>

        <div className="grid flex-1 items-center gap-12 px-6 py-12 sm:px-10 lg:grid-cols-[1.25fr_0.75fr] lg:px-16 lg:py-16">
          <section>
            <p className="mb-5 font-mono text-xs font-semibold uppercase tracking-[0.2em] text-[#175bd8]">
              Evidence-grounded product planning
            </p>
            <h1 className="max-w-3xl font-['Arial_Narrow','Aptos_Display',sans-serif] text-[clamp(3.4rem,8vw,7.4rem)] font-bold leading-[0.83] tracking-[-0.065em] text-[#102943]">
              App Review
              <br />
              Insights
            </h1>
            <p className="mt-7 max-w-xl text-base leading-7 text-[#61748a] sm:text-lg sm:leading-8">
              The application shell is ready. Domain contracts preserve the path from source review to verifiable product test.
            </p>

            <div className="mt-10 flex max-w-2xl flex-wrap items-center gap-y-3" aria-label="Core traceability chain">
              {traceSteps.map((step, index) => (
                <div className="flex items-center" key={step}>
                  <span className="rounded-full border border-[#cbdbea] bg-white px-3 py-1.5 font-mono text-[0.68rem] font-semibold uppercase tracking-[0.11em] text-[#385573]">
                    {step}
                  </span>
                  {index < traceSteps.length - 1 ? (
                    <span className="h-px w-5 bg-[#82a5ca] sm:w-8" aria-hidden="true" />
                  ) : null}
                </div>
              ))}
            </div>
          </section>

          <aside className="lg:justify-self-end lg:w-full lg:max-w-sm">
            <div className="mb-3 flex items-end justify-between px-1">
              <div>
                <p className="font-mono text-[0.68rem] uppercase tracking-[0.16em] text-[#7b8ca0]">System check</p>
                <h2 className="mt-1 text-xl font-semibold tracking-[-0.03em]">Backend Connection Status</h2>
              </div>
              <span className="font-mono text-[0.65rem] text-[#8495a8]">GET /api/health</span>
            </div>
            <BackendStatus connection={connection} />
          </aside>
        </div>

        <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-[#dce7f1] px-6 py-4 font-mono text-[0.65rem] uppercase tracking-[0.13em] text-[#788a9e] sm:px-10">
          <span>React + FastAPI</span>
          <span>No analysis pipeline active</span>
        </footer>
      </div>
    </main>
  )
}
