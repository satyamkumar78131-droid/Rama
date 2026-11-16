import { useEffect, useRef, useState } from 'react'

/* 🎙️ Live Baat — Gemini Live jaisa, par turn-based (free, in-browser).
   Loop: suno → /chat (hamesha mode 'fast') → jawab bolo → phir suno.
   Beech me tokna (interrupt) nahi hota — ek baari me ek bolega.
   Backend ko Live khulte hi /health se jaga diya jata hai (Render sleep). */

export default function LiveVoice({ api, onSend, onClose }) {
  const [phase, setPhase] = useState('idle') // idle | listening | thinking | speaking | error
  const [transcript, setTranscript] = useState('')
  const [reply, setReply] = useState('')
  const [muted, setMuted] = useState(false)
  const [started, setStarted] = useState(false)
  const [error, setError] = useState('')
  const [srSupported] = useState(() => {
    try { return !!(window.SpeechRecognition || window.webkitSpeechRecognition) } catch (e) { return false }
  })
  const [ttsSupported] = useState(() => {
    try { return 'speechSynthesis' in window } catch (e) { return false }
  })

  const recRef = useRef(null)
  const stoppedRef = useRef(false)
  const mutedRef = useRef(false)
  const phaseRef = useRef('idle')
  const finalRef = useRef('')
  const intentionalStopRef = useRef(false)
  const restartTimerRef = useRef(null)
  const processingRef = useRef(false)
  const voicesRef = useRef([])

  /* ---------- Awaaz ki voices: Android pe der se load hoti hain ---------- */
  function loadVoices() {
    try {
      const vs = window.speechSynthesis.getVoices() || []
      if (vs.length) voicesRef.current = vs
      return vs
    } catch (e) { return [] }
  }

  useEffect(() => {
    loadVoices()
    const onVoices = () => loadVoices()
    try { window.speechSynthesis?.addEventListener('voiceschanged', onVoices) } catch (e) { /* ignore */ }
    return () => { try { window.speechSynthesis?.removeEventListener('voiceschanged', onVoices) } catch (e) { /* ignore */ } }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function setPhaseBoth(p) {
    phaseRef.current = p
    setPhase(p)
  }

  /* ---------- Live khulte hi backend jagao (Render free tier sota hai) ---------- */
  useEffect(() => {
    try { fetch(`${api}/health`).catch(() => {}) } catch (e) { /* ignore */ }
    if (!srSupported) {
      setError('Is browser me live voice nahi chalti')
      setPhaseBoth('error')
    }
    return () => { stopAll() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => { mutedRef.current = muted }, [muted])

  function stopAll() {
    stoppedRef.current = true
    if (restartTimerRef.current) { clearTimeout(restartTimerRef.current); restartTimerRef.current = null }
    try { recRef.current?.stop() } catch (e) { /* ignore */ }
    recRef.current = null
    try { window.speechSynthesis?.cancel() } catch (e) { /* ignore */ }
  }

  function hangUp() {
    stopAll()
    onClose()
  }

  /* ---------- Jawab bolna (hi-IN voice, rate 1.0) ----------
     Android Chrome pe lamba text ek saath bolne pe awaaz hi nahi aati —
     isliye jawab ko chhote tukdon me bolte hain, ek ke baad ek.
     Agar onend/onerror na aaye to watchdog aage badha deta hai (loop atakega nahi). */
  function splitSentences(text) {
    const parts = String(text).replace(/\*\*/g, '').split(/(?<=[.!?।\n])\s+/)
    const chunks = []
    for (const p of parts) {
      const t = p.trim()
      if (!t) continue
      if (t.length <= 160) { chunks.push(t); continue }
      const words = t.split(/\s+/)
      let cur = ''
      for (const w of words) {
        if ((cur + ' ' + w).trim().length > 160 && cur) { chunks.push(cur.trim()); cur = w }
        else cur = (cur + ' ' + w).trim()
      }
      if (cur) chunks.push(cur.trim())
    }
    return chunks.length ? chunks : [String(text)]
  }

  function pickVoice() {
    const voices = voicesRef.current.length ? voicesRef.current : loadVoices()
    const hi = voices.find((v) => v.lang && v.lang.toLowerCase().startsWith('hi'))
    if (hi) return hi
    // Hindi voice phone me installed nahi hai to default voice se bolo — khamoshi se behtar
    return voices.length ? voices[0] : null
  }

  function speak(text, after) {
    if (!ttsSupported || !text) { if (after) after(); return }
    const chunks = splitSentences(text)
    let idx = 0
    let done = false
    const finish = () => { if (!done) { done = true; if (after) after() } }
    const speakChunk = () => {
      if (stoppedRef.current) { finish(); return }
      if (idx >= chunks.length) { finish(); return }
      const part = chunks[idx++]
      try {
        const u = new SpeechSynthesisUtterance(part)
        u.lang = 'hi-IN'
        u.rate = 1.0
        const v = pickVoice()
        if (v) u.voice = v
        let advanced = false
        let watchdog = null
        const next = () => {
          if (advanced) return
          advanced = true
          if (watchdog) clearTimeout(watchdog)
          setTimeout(speakChunk, 60)
        }
        watchdog = setTimeout(next, Math.max(5000, part.length * 120))
        u.onend = next
        u.onerror = next
        window.speechSynthesis.speak(u)
      } catch (e) {
        finish()
      }
    }
    try { window.speechSynthesis.cancel() } catch (e) { /* ignore */ }
    // Voices abhi load nahi hui to thoda ruko, phir bolo
    if (!voicesRef.current.length && !loadVoices().length) {
      setTimeout(speakChunk, 600)
    } else {
      setTimeout(speakChunk, 80)
    }
  }

  /* ---------- Awaaz test: ek chhoti line bol kar dikhao ---------- */
  function testVoice() {
    setError('')
    speak('Namaste, main Rama hoon. Kya tum mujhe sun pa rahe ho?', null)
  }

  /* ---------- Sunna shuru karo (loop ka ek round) ---------- */
  function startListening() {
    if (stoppedRef.current || mutedRef.current || processingRef.current) return
    if (recRef.current) return
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) {
      setError('Is browser me live voice nahi chalti')
      setPhaseBoth('error')
      return
    }
    try {
      const rec = new SR()
      rec.lang = 'hi-IN'
      rec.continuous = true
      rec.interimResults = true
      finalRef.current = ''
      intentionalStopRef.current = false
      rec.onresult = (ev) => {
        let interim = ''
        let gotFinal = false
        for (let i = ev.resultIndex; i < ev.results.length; i++) {
          const r = ev.results[i]
          if (r.isFinal) { finalRef.current += r[0].transcript; gotFinal = true }
          else interim += r[0].transcript
        }
        setTranscript((finalRef.current + ' ' + interim).trim())
        if (gotFinal) {
          const text = finalRef.current.trim()
          intentionalStopRef.current = true
          try { rec.stop() } catch (e) { /* ignore */ }
          if (text) processTurn(text)
          else if (!stoppedRef.current) scheduleRestart(300)
        }
      }
      rec.onerror = (ev) => {
        const err = ev && ev.error
        if (err === 'aborted') return
        if (err === 'not-allowed' || err === 'service-not-allowed') {
          recRef.current = null
          setError('Mic ki permission nahi mili — browser settings me allow karo.')
          setPhaseBoth('error')
          return
        }
        // no-speech / network / audio-capture: loop ko marne mat do, dobara suno
        recRef.current = null
        if (!stoppedRef.current && !mutedRef.current) scheduleRestart(err === 'network' ? 1000 : 500)
      }
      rec.onend = () => {
        recRef.current = null
        if (stoppedRef.current || intentionalStopRef.current) return
        if (mutedRef.current || processingRef.current) return
        if (phaseRef.current === 'listening') scheduleRestart(200)
      }
      recRef.current = rec
      rec.start()
      setPhaseBoth('listening')
    } catch (e) {
      recRef.current = null
      if (!stoppedRef.current) scheduleRestart(800)
    }
  }

  function scheduleRestart(ms) {
    if (stoppedRef.current) return
    if (restartTimerRef.current) clearTimeout(restartTimerRef.current)
    restartTimerRef.current = setTimeout(() => {
      restartTimerRef.current = null
      if (!stoppedRef.current && !mutedRef.current && !processingRef.current) startListening()
    }, ms)
  }

  /* ---------- Ek turn: /chat (hamesha fast) → jawab bolo → phir suno ---------- */
  async function processTurn(text) {
    if (stoppedRef.current) return
    processingRef.current = true
    setPhaseBoth('thinking')
    let answer = null
    try {
      answer = await onSend(text, 'fast') // Live me hamesha fast mode
    } catch (e) {
      answer = null
    }
    processingRef.current = false
    if (stoppedRef.current) return
    if (answer && String(answer).trim()) {
      setReply(String(answer))
      setPhaseBoth('speaking')
      speak(String(answer), () => {
        if (stoppedRef.current) return
        if (mutedRef.current) setPhaseBoth('idle')
        else startListening()
      })
    } else {
      // /chat fail (retry bhi ho chuka): atakna nahi — bol ke phir suno
      setReply('')
      setTranscript('dobara sun raha hoon')
      setPhaseBoth('listening')
      speak('dobara sun raha hoon', () => {
        if (!stoppedRef.current) startListening()
      })
    }
  }

  function startLive() {
    if (!srSupported) {
      setError('Is browser me live voice nahi chalti')
      setPhaseBoth('error')
      return
    }
    stoppedRef.current = false
    setStarted(true)
    setError('')
    setTranscript('')
    setReply('')
    startListening()
  }

  function retryLive() {
    stoppedRef.current = false
    setError('')
    setStarted(true)
    startListening()
  }

  function toggleMute() {
    const next = !muted
    setMuted(next)
    mutedRef.current = next
    if (next) {
      // Mic band: sunna roko (bolna chalta rahega)
      if (restartTimerRef.current) { clearTimeout(restartTimerRef.current); restartTimerRef.current = null }
      try { recRef.current?.stop() } catch (e) { /* ignore */ }
      recRef.current = null
      if (phaseRef.current === 'listening') setPhaseBoth('idle')
    } else if (!stoppedRef.current && !processingRef.current) {
      startListening()
    }
  }

  function statusText() {
    if (muted && (phase === 'listening' || phase === 'idle')) return '🔇 Mic band hai'
    switch (phase) {
      case 'listening': return '👂 Sun raha hoon...'
      case 'thinking': return '🤔 RAMA soch raha hai...'
      case 'speaking': return '🔊 RAMA bol raha hai...'
      case 'error': return 'Kuch ruk gaya'
      default: return 'Bolo, main sun raha hoon...'
    }
  }

  const orbClass = phase === 'listening' ? 'listening'
    : phase === 'speaking' ? 'speaking'
    : phase === 'thinking' ? 'thinking' : ''

  return (
    <div className="live-overlay">
      <div className="live-top">
        <span className="live-title">🎙️ Live Baat</span>
        <button type="button" className="live-close" onClick={hangUp} aria-label="Band karo">✕</button>
      </div>

      <div className={`live-orb ${orbClass}`}>
        {phase === 'speaking' ? '🔊' : phase === 'thinking' ? '🤔' : '🎙️'}
      </div>

      <div className="live-status">{statusText()}</div>

      {phase === 'error' ? (
        <div className="live-error">
          <p>{error}</p>
          <button type="button" className="live-retry-btn" onClick={retryLive}>Dobara try karo</button>
        </div>
      ) : !started ? (
        <>
          <p className="live-intro">Mic dabao, bolo — RAMA bol kar jawab dega. Baat khatm karne ke liye 📞 Band karo dabao.</p>
          <button type="button" className="live-start-btn" onClick={startLive}>🎙️ Live shuru karo</button>
          <button type="button" className="live-retry-btn" onClick={testVoice}>🔊 Awaaz check karo</button>
        </>
      ) : (
        <>
          {transcript && (
            <div className="live-box">
              <div className="live-box-label">Tumne kaha:</div>
              <div className="live-box-text">{transcript}</div>
            </div>
          )}
          {reply && (
            <div className="live-box live-reply-box">
              <div className="live-box-label">RAMA:</div>
              <div className="live-box-text">{reply.replace(/\*\*/g, '')}</div>
            </div>
          )}
          <div className="live-controls">
            <button type="button" className="live-hangup" onClick={hangUp}>📞 Band karo</button>
            <button type="button" className="live-mute" onClick={toggleMute}>
              {muted ? '🎤 Unmute' : '🔇 Mute'}
            </button>
            <button type="button" className="live-retry-btn" onClick={testVoice}>🔊 Awaaz check</button>
          </div>
        </>
      )}

      {!ttsSupported && phase !== 'error' && (
        <p className="live-note">Is browser me bol kar sunana nahi chalega — jawab text me dikhega.</p>
      )}
      <p className="live-note">Turn-based hai — ek baari me ek bolega. Fast mode me jawab aata hai.</p>
    </div>
  )
}
