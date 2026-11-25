import { useEffect, useRef, useState, useCallback } from 'react'
import { Link } from 'react-router-dom'

const TOTAL_FRAMES = 241
const FRAME_PATH = (index) => `/frames/frame_${String(index).padStart(4, '0')}.jpg`

const STORY_SECTIONS = [
  {
    id: 'ai-radiology',
    navLabel: 'AI in Radiology',
    positionClass: 'left-4 sm:left-10 lg:left-16 top-20 sm:top-[12%]',
    range: [0.00, 0.24],
    step: '01 / 04',
    badge: 'CLINICAL AI & RADIOLOGY',
    title: 'The Transformative Power of AI in Diagnostic Radiology',
    paragraphs: [
      'Artificial intelligence has ushered in a new frontier for medical imaging. Deep convolutional networks and vision transformers accelerate early pathology detection, flag subtle anomalies, and triage emergency cases with high consistency.',
      'From cranial CT surveys to full-skeletal radiographic scans, neural networks process high-dimensional volumes in seconds—providing clinicians with dependable diagnostic support.'
    ],
    highlight: 'Deep models excel at spotting microscopic markers, but clinical reliability requires high dataset diversity.',
    metric: { value: '99.2%', label: 'Benchmark target for clinical diagnostic classifiers' }
  },
  {
    id: 'rare-diseases',
    navLabel: 'Data Scarcity',
    positionClass: 'right-4 sm:right-10 lg:right-16 top-24 sm:top-[26%]',
    range: [0.24, 0.49],
    step: '02 / 04',
    badge: 'THE DATA BOTTLENECK',
    title: 'The Scarcity Dilemma in Rare Pathology Classification',
    paragraphs: [
      'While common conditions have abundant training samples, rare anatomical disorders and bone lesions appear only a few times in any single hospital’s archive, creating severe class imbalance.',
      'When deep learning models are trained on scarce archives, they overfit to patient-specific artifacts rather than learning true disease markers, risking elevated false negatives in clinical deployment.'
    ],
    highlight: 'Rare pathologies account for <1% of typical hospital repositories, causing standard classifiers to collapse on minority classes.',
    metric: { value: '< 1%', label: 'Minority pathology representation in typical archives' }
  },
  {
    id: 'our-solution',
    navLabel: 'Augment Pipeline',
    positionClass: 'left-4 sm:left-10 lg:left-16 top-24 sm:top-[42%]',
    range: [0.49, 0.74],
    step: '03 / 04',
    badge: 'MEDAUGMENT PIPELINE',
    title: 'Diagnostic-Preserving Geometric & Intensity Augmentation',
    paragraphs: [
      'MedAugment overcomes data scarcity through a strictly non-generative pipeline. Unlike synthetic generators that risk hallucinating false lesions, our pipeline preserves diagnostic anatomical truth.',
      'By applying conservative rotation, elastic deformation, and HU intensity scaling, MedAugment multiplies scarce cohorts by 5x–20x while modeling natural tissue plasticity and scanner variations.'
    ],
    highlight: 'Deterministic, provenance-tracked transforms multiply training data without synthetic hallucination risks.',
    features: ['Elastic Tissue Deformation', 'Conservative Rotation', 'HU Intensity Scaling', 'Cryptographic Lineage']
  },
  {
    id: 'implementation',
    navLabel: 'Studio & Launch',
    positionClass: 'right-4 sm:right-10 lg:right-16 top-24 sm:top-[46%]',
    range: [0.74, 1.00],
    step: '04 / 04',
    badge: 'STUDIO IMPLEMENTATION',
    title: 'Production-Ready Dataset Studio & Pipeline Execution',
    paragraphs: [
      'MedAugment provides an end-to-end studio for clinical ML engineers. Upload DICOM/scan archives, configure transformation matrices, and balance class distributions in real time.',
      'Audit every transformed sample with side-by-side inspection, and export verified datasets with full cryptographic provenance manifests for reproducible training.'
    ],
    highlight: 'Seamlessly bridge the gap between sparse clinical data and production-grade diagnostic AI.',
    cta: true
  }
]

// 3D Receding Effect: text cards move back into z-space as you scroll
function getCard3DTransition(progress, index) {
  const windows = [
    { fadeIn: 0.00, peakStart: 0.00, peakEnd: 0.15, fadeOut: 0.28 }, // 1 (Left Top)
    { fadeIn: 0.16, peakStart: 0.29, peakEnd: 0.41, fadeOut: 0.54 }, // 2 (Right Mid Top)
    { fadeIn: 0.42, peakStart: 0.55, peakEnd: 0.67, fadeOut: 0.80 }, // 3 (Left Mid Bottom)
    { fadeIn: 0.68, peakStart: 0.81, peakEnd: 1.00, fadeOut: 1.00 }, // 4 (Right Mid Bottom)
  ]

  const w = windows[index]
  if (progress < w.fadeIn || progress > w.fadeOut) {
    return {
      opacity: 0,
      transform: 'perspective(1000px) translateZ(-200px) scale(0.78) rotateX(4deg)',
      blur: 4,
      visible: false
    }
  }

  let opacity = 1
  let z = 0
  let scale = 1.0
  let blur = 0
  const isLeft = index % 2 === 0
  let rotY = isLeft ? 5 : -5
  const rotX = 3

  if (progress < w.peakStart) {
    // Coming into view (from near camera)
    const t = (progress - w.fadeIn) / Math.max(0.001, w.peakStart - w.fadeIn)
    opacity = t
    z = 30 * (1 - t)
    scale = 1.02 - 0.02 * t
    blur = 0
  } else if (progress <= w.peakEnd) {
    // In sharp focus
    opacity = 1
    z = 0
    scale = 1.0
    blur = 0
  } else {
    // Receding deep away from the camera as user scrolls!
    const t = (progress - w.peakEnd) / Math.max(0.001, w.fadeOut - w.peakEnd)
    opacity = Math.max(0, 1 - t)
    z = -200 * t          // Moves deep into 3D z-space
    scale = 1.0 - 0.22 * t // Shrinks with perspective distance
    blur = 3.5 * t         // Depth of field blur as it moves away
    rotY = (isLeft ? 5 : -5) * (1 + t * 0.4)
  }

  return {
    opacity: Math.max(0, Math.min(1, opacity)),
    transform: `perspective(1000px) translateZ(${z.toFixed(1)}px) scale(${scale.toFixed(3)}) rotateY(${rotY.toFixed(1)}deg) rotateX(${rotX}deg)`,
    blur: blur.toFixed(1),
    visible: opacity > 0.01
  }
}

export default function LandingPage() {
  const containerRef = useRef(null)
  const canvasRef = useRef(null)
  const imagesRef = useRef(new Map())
  const [activeSectionIndex, setActiveSectionIndex] = useState(0)
  const [scrollProgress, setScrollProgress] = useState(0)
  const [currentFrame, setCurrentFrame] = useState(1)
  const rafRef = useRef(null)
  const lastDrawnFrameRef = useRef(null)

  // Draw a frame to canvas keeping aspect ratio (cover/center)
  const drawFrame = useCallback((frameNumber) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // Find requested image or closest loaded frame
    let img = imagesRef.current.get(frameNumber)
    if (!img || !img.complete) {
      let nearestDist = Infinity
      let nearestFrame = 1
      for (const [k, v] of imagesRef.current.entries()) {
        if (v && v.complete && Math.abs(k - frameNumber) < nearestDist) {
          nearestDist = Math.abs(k - frameNumber)
          nearestFrame = k
        }
      }
      img = imagesRef.current.get(nearestFrame)
    }

    if (!img || !img.complete) return

    lastDrawnFrameRef.current = frameNumber

    // Set canvas internal resolution to match display size * DPR
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    const rect = canvas.getBoundingClientRect()
    const targetW = Math.round(rect.width * dpr)
    const targetH = Math.round(rect.height * dpr)

    if (canvas.width !== targetW || canvas.height !== targetH) {
      canvas.width = targetW
      canvas.height = targetH
    }

    ctx.save()
    ctx.scale(dpr, dpr)

    const w = rect.width
    const h = rect.height
    const imgRatio = img.width / img.height
    const canvasRatio = w / h

    let drawW, drawH, offsetX, offsetY

    if (canvasRatio > imgRatio) {
      drawW = w
      drawH = w / imgRatio
      offsetX = 0
      offsetY = (h - drawH) / 2
    } else {
      drawH = h
      drawW = h * imgRatio
      offsetX = (w - drawW) / 2
      offsetY = 0
    }

    ctx.fillStyle = '#070A11'
    ctx.fillRect(0, 0, w, h)
    ctx.drawImage(img, offsetX, offsetY, drawW, drawH)
    ctx.restore()
  }, [])

  // Preload frames in priority order
  useEffect(() => {
    let isCancelled = false

    // 1. Immediately preload frame 1 for instant first paint
    const firstImg = new Image()
    firstImg.src = FRAME_PATH(1)
    firstImg.onload = () => {
      if (isCancelled) return
      imagesRef.current.set(1, firstImg)
      drawFrame(1)
    }

    // 2. Preload queue (key intervals first for immediate scrubbing response)
    const preloadQueue = []
    for (let i = 1; i <= TOTAL_FRAMES; i += 4) {
      preloadQueue.push(i)
    }
    for (let i = 1; i <= TOTAL_FRAMES; i++) {
      if (i % 4 !== 1) preloadQueue.push(i)
    }

    const loadNextBatch = (batchStartIndex, batchSize) => {
      if (isCancelled || batchStartIndex >= preloadQueue.length) return

      const batch = preloadQueue.slice(batchStartIndex, batchStartIndex + batchSize)
      let batchLoaded = 0

      batch.forEach((frameIdx) => {
        if (imagesRef.current.has(frameIdx)) {
          batchLoaded++
          if (batchLoaded === batch.length) {
            loadNextBatch(batchStartIndex + batchSize, batchSize)
          }
          return
        }

        const img = new Image()
        img.src = FRAME_PATH(frameIdx)
        img.onload = () => {
          if (isCancelled) return
          imagesRef.current.set(frameIdx, img)
          batchLoaded++
          if (batchLoaded === batch.length) {
            loadNextBatch(batchStartIndex + batchSize, batchSize)
          }
        }
        img.onerror = () => {
          batchLoaded++
          if (batchLoaded === batch.length) {
            loadNextBatch(batchStartIndex + batchSize, batchSize)
          }
        }
      })
    }

    loadNextBatch(0, 14)

    return () => {
      isCancelled = true
    }
  }, [drawFrame])

  // Handle scroll and animation sync
  useEffect(() => {
    const handleScroll = () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)

      rafRef.current = requestAnimationFrame(() => {
        const container = containerRef.current
        if (!container) return

        const rect = container.getBoundingClientRect()
        const totalScrollable = container.offsetHeight - window.innerHeight
        if (totalScrollable <= 0) return

        const scrolled = -rect.top
        const progress = Math.min(Math.max(scrolled / totalScrollable, 0), 1)
        setScrollProgress(progress)

        // Map progress to frame 1 -> 241
        const targetFrame = Math.min(
          Math.floor(progress * (TOTAL_FRAMES - 1)) + 1,
          TOTAL_FRAMES
        )
        setCurrentFrame(targetFrame)
        drawFrame(targetFrame)

        // Determine currently active section index based on scroll depth
        let activeIdx = 0
        if (progress < 0.24) {
          activeIdx = 0
        } else if (progress < 0.49) {
          activeIdx = 1
        } else if (progress < 0.74) {
          activeIdx = 2
        } else {
          activeIdx = 3
        }
        setActiveSectionIndex(activeIdx)
      })
    }

    window.addEventListener('scroll', handleScroll, { passive: true })
    window.addEventListener('resize', () => {
      if (lastDrawnFrameRef.current) drawFrame(lastDrawnFrameRef.current)
    })

    return () => {
      window.removeEventListener('scroll', handleScroll)
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
    }
  }, [drawFrame])

  // Reliable cross-browser smooth scroll animation using requestAnimationFrame
  const smoothScrollTo = useCallback((targetY, duration = 650) => {
    const startY = window.scrollY || window.pageYOffset || document.documentElement.scrollTop || 0
    const diff = targetY - startY
    if (Math.abs(diff) < 2) return

    let start = null
    const step = (timestamp) => {
      if (!start) start = timestamp
      const elapsed = timestamp - start
      const p = Math.min(elapsed / duration, 1)
      // easeInOutCubic curve for silky smooth momentum
      const ease = p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2
      window.scrollTo(0, Math.round(startY + diff * ease))

      if (p < 1) {
        requestAnimationFrame(step)
      }
    }
    requestAnimationFrame(step)
  }, [])

  // Scroll smoothly to a specific milestone
  const scrollToSection = useCallback((index) => {
    const container = containerRef.current
    if (!container) return
    const containerTop = container.getBoundingClientRect().top + (window.scrollY || window.pageYOffset || document.documentElement.scrollTop || 0)
    const totalScrollable = container.offsetHeight - window.innerHeight
    if (totalScrollable <= 0) return

    // Explicit targets corresponding to each card's optimal viewing progress
    const targets = [0.0, 0.35, 0.61, 0.88]
    const targetProgress = targets[index] ?? 0
    const targetY = Math.round(containerTop + targetProgress * totalScrollable)

    smoothScrollTo(targetY)
  }, [smoothScrollTo])

  return (
    <div className="relative min-h-screen bg-[#070A11] text-slate-100 font-sans selection:bg-teal-500/30 selection:text-teal-200">
      {/* Fixed Sticky Header */}
      <header className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 py-4 backdrop-blur-xl bg-[#070A11]/75 border-b border-white/10 transition-all duration-300">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-teal-500 to-indigo-600 shadow-lg shadow-teal-500/25">
            <svg className="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 2h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 8.172V3L8 2z" />
            </svg>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-base font-extrabold tracking-tight text-white">MedAugment</span>
              <span className="rounded bg-teal-500/20 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-teal-300 border border-teal-500/30">AI</span>
            </div>
            <p className="text-xs text-slate-400 font-medium hidden sm:block">Radiology Rare-Condition Pipeline</p>
          </div>
        </div>

        {/* Meaningful Story Section Indicator Pills */}
        <div className="flex items-center gap-1.5 sm:gap-2 bg-slate-900/70 p-1 sm:p-1.5 rounded-full border border-white/10 backdrop-blur-md max-w-[55vw] sm:max-w-none overflow-x-auto no-scrollbar">
          {STORY_SECTIONS.map((sec, idx) => {
            const isActive = activeSectionIndex === idx
            return (
              <button
                key={sec.id}
                type="button"
                onClick={(e) => {
                  e.preventDefault()
                  e.stopPropagation()
                  scrollToSection(idx)
                }}
                className={`px-2.5 sm:px-3.5 py-1 text-[11px] sm:text-xs font-semibold rounded-full transition-all duration-300 flex items-center gap-1 sm:gap-1.5 whitespace-nowrap cursor-pointer select-none ${
                  isActive
                    ? 'bg-gradient-to-r from-teal-500 to-indigo-600 text-white shadow-md shadow-teal-500/30 ring-1 ring-white/20'
                    : 'text-slate-400 hover:text-white hover:bg-white/10'
                }`}
              >
                <span className="opacity-75">{idx + 1}.</span>
                <span>{sec.navLabel}</span>
              </button>
            )
          })}
        </div>

        {/* Launch App Main CTA */}
        <div className="flex items-center gap-3">
          <Link
            to="/app"
            className="group relative inline-flex items-center gap-2 overflow-hidden rounded-xl bg-gradient-to-r from-teal-500 via-teal-400 to-indigo-600 px-5 py-2.5 text-xs sm:text-sm font-bold text-white shadow-lg shadow-teal-500/30 transition-all duration-300 hover:shadow-teal-500/50 hover:brightness-110 active:scale-95"
          >
            <span>Launch App</span>
            <svg className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M14 5l7 7m0 0l-7 7m7-7H3" />
            </svg>
          </Link>
        </div>
      </header>

      {/* Top Progress Line */}
      <div className="fixed top-0 left-0 right-0 h-[3px] bg-slate-800 z-50">
        <div
          className="h-full bg-gradient-to-r from-teal-400 to-indigo-500 transition-all duration-75 ease-out"
          style={{ width: `${Math.round(scrollProgress * 100)}%` }}
        />
      </div>

      {/* Scrollytelling Pinned Section */}
      <div ref={containerRef} className="relative h-[480vh] w-full">
        {/* Sticky Viewport with 3D perspective */}
        <div
          className="sticky top-0 h-screen w-full overflow-hidden flex items-center justify-center"
          style={{ perspective: '1200px' }}
        >
          {/* Canvas Background for Skeleton Video Frames */}
          <canvas
            ref={canvasRef}
            className="absolute inset-0 h-full w-full object-cover"
          />

          {/* Vignette Overlays for Text Contrast (both left and right sides) */}
          <div className="absolute inset-y-0 left-0 w-full md:w-2/5 bg-gradient-to-r from-[#070A11]/85 via-[#070A11]/35 to-transparent pointer-events-none" />
          <div className="absolute inset-y-0 right-0 w-full md:w-2/5 bg-gradient-to-l from-[#070A11]/85 via-[#070A11]/35 to-transparent pointer-events-none" />
          <div className="absolute inset-0 bg-gradient-to-t from-[#070A11] via-transparent to-[#070A11]/60 pointer-events-none" />
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_40%,rgba(7,10,17,0.75)_100%)] pointer-events-none" />

          {/* Clean Telemetry HUD: Frame X / 241 */}
          <div className="absolute right-6 top-20 z-30 pointer-events-none hidden sm:block">
            <div className="flex items-center gap-2 rounded-lg bg-black/60 border border-white/10 px-3 py-1.5 backdrop-blur-md shadow-lg">
              <div className="h-2 w-2 rounded-full bg-teal-400 animate-pulse" />
              <span className="text-[11px] font-mono tracking-wider text-slate-300">
                FRAME <span className="font-bold text-white">{currentFrame}</span> <span className="text-slate-500">/ {TOTAL_FRAMES}</span>
              </span>
            </div>
          </div>

          {/* Alternating 3D Story Cards */}
          <div className="absolute inset-0 z-20 pointer-events-none">
            {STORY_SECTIONS.map((section, idx) => {
              const { opacity, transform, blur, visible } = getCard3DTransition(scrollProgress, idx)
              const isLeft = idx % 2 === 0

              return (
                <div
                  key={section.id}
                  style={{
                    opacity,
                    transform,
                    filter: `blur(${blur}px)`,
                    pointerEvents: visible && opacity > 0.4 ? 'auto' : 'none',
                    display: visible ? 'block' : 'none',
                    transformStyle: 'preserve-3d',
                    willChange: 'transform, opacity, filter',
                    transition: 'box-shadow 0.3s ease'
                  }}
                  className={`absolute w-[92vw] sm:w-[410px] max-w-[420px] ${section.positionClass}`}
                >
                  <div
                    className="rounded-2xl border border-white/15 bg-slate-900/85 p-5 sm:p-6 shadow-2xl backdrop-blur-xl relative overflow-hidden group"
                    style={{
                      boxShadow: '0 20px 40px -15px rgba(0, 0, 0, 0.7), 0 0 25px -5px rgba(13, 148, 136, 0.15)',
                    }}
                  >
                    {/* Subtle 3D corner ambient light */}
                    <div
                      className={`absolute -top-12 h-28 w-28 rounded-full blur-2xl pointer-events-none ${
                        isLeft ? '-left-12 bg-teal-500/20' : '-right-12 bg-indigo-500/20'
                      }`}
                    />

                    {/* Step & Badge */}
                    <div className="flex items-center gap-2.5 mb-2.5">
                      <span className="text-[11px] font-mono font-bold tracking-widest text-teal-400 uppercase">
                        {section.step}
                      </span>
                      <span className="h-1 w-1 rounded-full bg-slate-500" />
                      <span className="rounded-full bg-teal-500/10 px-2.5 py-0.5 text-[10px] font-bold tracking-wider text-teal-300 border border-teal-500/20">
                        {section.badge}
                      </span>
                    </div>

                    {/* Heading */}
                    <h2 className="text-lg sm:text-xl font-extrabold tracking-tight text-white leading-snug mb-3">
                      {section.title}
                    </h2>

                    {/* Paragraphs */}
                    <div className="space-y-2 text-slate-300 text-xs sm:text-[13px] leading-relaxed mb-4">
                      {section.paragraphs.map((p, pIdx) => (
                        <p key={pIdx}>{p}</p>
                      ))}
                    </div>

                    {/* Highlight Box */}
                    {section.highlight && (
                      <div className="rounded-xl border border-teal-500/30 bg-teal-950/40 p-3 text-[11px] sm:text-xs text-teal-200/90 leading-relaxed mb-3.5 flex items-start gap-2">
                        <svg className="h-4 w-4 text-teal-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <span>{section.highlight}</span>
                      </div>
                    )}

                    {/* Metric */}
                    {section.metric && (
                      <div className="flex items-center gap-3 pt-2.5 border-t border-white/10">
                        <div className="text-xl sm:text-2xl font-black text-transparent bg-clip-text bg-gradient-to-r from-teal-400 to-indigo-400">
                          {section.metric.value}
                        </div>
                        <div className="text-[11px] text-slate-400 font-medium">
                          {section.metric.label}
                        </div>
                      </div>
                    )}

                    {/* Feature tags */}
                    {section.features && (
                      <div className="flex flex-wrap gap-1.5 pt-2 border-t border-white/10">
                        {section.features.map((feat) => (
                          <span key={feat} className="rounded-md bg-white/5 px-2 py-0.5 text-[11px] font-semibold text-slate-200 border border-white/10">
                            ✓ {feat}
                          </span>
                        ))}
                      </div>
                    )}

                    {/* CTA on final card */}
                    {section.cta && (
                      <div className="pt-3 border-t border-white/10 flex items-center gap-2.5">
                        <Link
                          to="/app"
                          className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-xl bg-gradient-to-r from-teal-500 to-indigo-600 px-4 py-2.5 text-xs font-bold text-white shadow-md shadow-teal-500/30 hover:brightness-110 active:scale-95 transition-all"
                        >
                          <span>Launch Studio</span>
                          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                          </svg>
                        </Link>
                        <Link
                          to="/datasets/new"
                          className="inline-flex items-center justify-center rounded-xl border border-white/20 bg-white/5 px-3 py-2.5 text-xs font-semibold text-slate-200 hover:bg-white/10 transition-all"
                        >
                          Upload
                        </Link>
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>

          {/* Bottom Scroll Prompt (Only at the start) */}
          <div
            className={`absolute bottom-8 left-1/2 -translate-x-1/2 z-20 flex flex-col items-center gap-2 transition-all duration-500 pointer-events-none ${
              scrollProgress > 0.08 ? 'opacity-0 translate-y-4' : 'opacity-100 translate-y-0'
            }`}
          >
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Scroll to Explore</span>
            <div className="h-9 w-5 rounded-full border-2 border-slate-500/60 p-1 flex justify-center">
              <div className="h-1.5 w-1 rounded-full bg-teal-400 animate-bounce" />
            </div>
          </div>

          {/* Quick Jump Sidebar Dots on Right */}
          <div className="absolute right-3 sm:right-6 top-1/2 -translate-y-1/2 hidden md:flex flex-col gap-2.5 z-30">
            {STORY_SECTIONS.map((sec, idx) => {
              const isActive = activeSectionIndex === idx
              return (
                <button
                  key={sec.id}
                  type="button"
                  onClick={(e) => {
                    e.preventDefault()
                    e.stopPropagation()
                    scrollToSection(idx)
                  }}
                  className="group relative flex items-center justify-end p-2 cursor-pointer select-none"
                  aria-label={`Jump to ${sec.navLabel}`}
                >
                  <span className="absolute right-7 rounded-lg bg-slate-900/95 px-2.5 py-1 text-[11px] font-semibold text-white opacity-0 transition-opacity duration-200 group-hover:opacity-100 border border-white/10 backdrop-blur-md whitespace-nowrap shadow-xl pointer-events-none">
                    {sec.navLabel}
                  </span>
                  <div
                    className={`h-3 w-3 rounded-full transition-all duration-300 ${
                      isActive
                        ? 'bg-teal-400 scale-125 ring-4 ring-teal-400/35'
                        : 'bg-slate-600 group-hover:bg-slate-400'
                    }`}
                  />
                </button>
              )
            })}
          </div>
        </div>
      </div>

      {/* Subsequent Landing Page Sections (Below the 480vh scroll fold) */}
      <section className="relative z-30 bg-[#0B0F19] border-t border-white/10 px-6 py-24 sm:px-12 lg:px-20">
        <div className="max-w-6xl mx-auto">
          {/* Section Header */}
          <div className="text-center max-w-3xl mx-auto mb-16">
            <span className="rounded-full bg-teal-500/10 px-3.5 py-1 text-xs font-bold uppercase tracking-wider text-teal-300 border border-teal-500/20">
              Core Architecture
            </span>
            <h2 className="mt-4 text-3xl sm:text-4xl font-extrabold text-white tracking-tight">
              Three Non-Generative Pillars of Diagnostic Augmentation
            </h2>
            <p className="mt-4 text-slate-400 text-base sm:text-lg">
              Radiology demands strict anatomical authenticity. Our pipeline applies clinically safe, deterministic physics-grounded transformations to multiply scarce rare-condition scans without synthetic artifacts.
            </p>
          </div>

          {/* 3 Pillars Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-20">
            <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-8 backdrop-blur-md hover:border-teal-500/40 transition-all duration-300 group">
              <div className="h-12 w-12 rounded-xl bg-teal-500/10 border border-teal-500/20 flex items-center justify-center text-teal-400 mb-6 group-hover:scale-110 transition-transform">
                <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              </div>
              <h3 className="text-xl font-bold text-white mb-3">Conservative Rotation</h3>
              <p className="text-sm text-slate-400 leading-relaxed mb-4">
                Simulates real-world patient positioning differences on CT/X-ray gantry beds while strictly preserving anatomical axis orientation and landmark coordinates.
              </p>
              <span className="text-xs font-semibold text-teal-400 flex items-center gap-1">
                ±15° clinical range • Zero anatomical inversion
              </span>
            </div>

            <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-8 backdrop-blur-md hover:border-indigo-500/40 transition-all duration-300 group">
              <div className="h-12 w-12 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 mb-6 group-hover:scale-110 transition-transform">
                <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M11 4a2 2 0 114 0v1a1 1 0 001 1h3a1 1 0 011 1v3a1 1 0 01-1 1h-1a2 2 0 100 4h1a1 1 0 011 1v3a1 1 0 01-1 1h-3a1 1 0 01-1-1v-1a2 2 0 10-4 0v1a1 1 0 01-1 1H7a1 1 0 01-1-1v-3a1 1 0 00-1-1H4a2 2 0 110-4h1a1 1 0 001-1V7a1 1 0 011-1h3a1 1 0 001-1V4z" />
                </svg>
              </div>
              <h3 className="text-xl font-bold text-white mb-3">Elastic Deformation</h3>
              <p className="text-sm text-slate-400 leading-relaxed mb-4">
                Employs smooth b-spline vector fields to model natural physiological tissue elasticity, visceral breathing excursions, and soft-tissue mechanical compliance.
              </p>
              <span className="text-xs font-semibold text-indigo-400 flex items-center gap-1">
                B-spline grid displacement • Morphological consistency
              </span>
            </div>

            <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-8 backdrop-blur-md hover:border-teal-500/40 transition-all duration-300 group">
              <div className="h-12 w-12 rounded-xl bg-teal-500/10 border border-teal-500/20 flex items-center justify-center text-teal-400 mb-6 group-hover:scale-110 transition-transform">
                <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                </svg>
              </div>
              <h3 className="text-xl font-bold text-white mb-3">Intensity Variation</h3>
              <p className="text-sm text-slate-400 leading-relaxed mb-4">
                Controls Hounsfield unit (HU) curves and contrast gradients to build invariance against multi-vendor scanner calibration drift (Siemens, GE, Philips).
              </p>
              <span className="text-xs font-semibold text-teal-400 flex items-center gap-1">
                Window-level scaling • Scanner-invariant training
              </span>
            </div>
          </div>

          {/* Workflow Sequence Banner */}
          <div className="rounded-3xl border border-white/10 bg-gradient-to-br from-slate-900 via-slate-950 to-[#0F172A] p-8 sm:p-12 shadow-2xl relative overflow-hidden">
            <div className="absolute -right-20 -top-20 h-64 w-64 rounded-full bg-teal-500/10 blur-3xl" />
            <div className="absolute -left-20 -bottom-20 h-64 w-64 rounded-full bg-indigo-500/10 blur-3xl" />

            <div className="relative z-10 flex flex-col lg:flex-row lg:items-center justify-between gap-8">
              <div className="max-w-xl">
                <span className="rounded-full bg-teal-500/10 px-3 py-1 text-xs font-bold uppercase tracking-wider text-teal-300 border border-teal-500/20">
                  Ready to deploy
                </span>
                <h3 className="mt-3 text-2xl sm:text-3xl font-extrabold text-white">
                  Balance Your Rare-Disease Cohorts Today
                </h3>
                <p className="mt-3 text-slate-300 text-sm sm:text-base leading-relaxed">
                  Enter the MedAugment studio to upload your dataset manifest, configure transformation parameters, trigger parallel processing jobs, and inspect cryptographic provenance manifests.
                </p>
              </div>

              <div className="flex flex-col sm:flex-row items-stretch gap-4 shrink-0">
                <Link
                  to="/app"
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-teal-500 via-teal-400 to-indigo-600 px-6 py-3.5 text-sm font-bold text-white shadow-xl shadow-teal-500/30 hover:brightness-110 active:scale-95 transition-all"
                >
                  <span>Launch Application</span>
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                  </svg>
                </Link>
                <Link
                  to="/datasets/new"
                  className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/20 bg-white/5 px-6 py-3.5 text-sm font-semibold text-slate-200 hover:bg-white/10 transition-all"
                >
                  Upload Dataset
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="relative z-30 border-t border-white/10 bg-[#070A11] px-6 py-10 text-center text-xs text-slate-500">
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="font-bold text-slate-300">MedAugment AI</span>
            <span>—</span>
            <span>Medical image augmentation pipeline for rare-condition classifier training</span>
          </div>
          <div className="flex items-center gap-4">
            <Link to="/app" className="hover:text-teal-400 transition-colors">Dashboard</Link>
            <Link to="/datasets/new" className="hover:text-teal-400 transition-colors">Upload</Link>
            <Link to="/jobs" className="hover:text-teal-400 transition-colors">Jobs</Link>
            <Link to="/exports" className="hover:text-teal-400 transition-colors">Exports</Link>
          </div>
        </div>
      </footer>
    </div>
  )
}
