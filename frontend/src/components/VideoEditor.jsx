import { useEffect, useRef, useState } from 'react'

const SPEEDS = [0.5, 1, 1.5, 2]

function fmt(t) {
  if (!isFinite(t) || t < 0) t = 0
  const m = Math.floor(t / 60)
  const s = Math.floor(t % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

function waitSeeked(video) {
  return new Promise((resolve) => {
    let done = false
    const finish = () => {
      if (!done) {
        done = true
        video.removeEventListener('seeked', finish)
        resolve()
      }
    }
    video.addEventListener('seeked', finish)
    setTimeout(finish, 3000)
  })
}

function seekToTime(video, t) {
  if (Math.abs(video.currentTime - t) < 0.05) return Promise.resolve()
  video.currentTime = t
  return waitSeeked(video)
}

function triggerDownload(url, filename) {
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 5000)
}

function drawTextOnCanvas(ctx, canvas, text, pos, size, scale) {
  const fontSize = Math.max(12, Math.round(size * scale))
  ctx.font = `bold ${fontSize}px system-ui, sans-serif`
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  const x = canvas.width / 2
  const y = pos === 'top' ? canvas.height * 0.12 : pos === 'center' ? canvas.height * 0.5 : canvas.height * 0.88
  ctx.lineWidth = Math.max(2, Math.round(fontSize / 8))
  ctx.strokeStyle = 'rgba(0,0,0,0.9)'
  ctx.fillStyle = '#ffffff'
  const lines = String(text).split('\n')
  const lh = fontSize * 1.25
  const startY = y - ((lines.length - 1) * lh) / 2
  lines.forEach((line, i) => {
    const ly = startY + i * lh
    ctx.strokeText(line, x, ly)
    ctx.fillText(line, x, ly)
  })
}

function loadImage(url) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    const timer = setTimeout(() => reject(new Error('photo load timeout')), 20000)
    img.onload = () => { clearTimeout(timer); resolve(img) }
    img.onerror = () => { clearTimeout(timer); reject(new Error('photo load nahi hui')) }
    img.src = url
  })
}

// Photo ko 6 second ka video clip banao (canvas + MediaRecorder, real-time).
// kenBurns = true: slow zoom + halka pan; false: static frame.
async function imageToClip(img, { durationSec = 6, kenBurns = true, onProgress } = {}) {
  const probe = document.createElement('canvas')
  if (typeof probe.captureStream !== 'function' || !window.MediaRecorder) {
    throw new Error('browser support nahi hai')
  }
  const canvas = document.createElement('canvas')
  canvas.width = 720
  canvas.height = 1280
  const ctx = canvas.getContext('2d')
  const stream = canvas.captureStream(30)
  const mime = ['video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm'].find((m) => {
    try { return window.MediaRecorder.isTypeSupported(m) } catch (e) { return false }
  })
  const rec = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream)
  const chunks = []
  rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data) }
  const stopped = new Promise((resolve) => { rec.onstop = resolve })
  const iw = img.naturalWidth || img.width
  const ih = img.naturalHeight || img.height
  const base = Math.max(canvas.width / iw, canvas.height / ih)
  const draw = (p) => {
    const zoom = kenBurns ? 1 + 0.14 * p : 1
    const dw = iw * base * zoom
    const dh = ih * base * zoom
    const drift = kenBurns ? (p - 0.5) * 36 : 0
    const dx = (canvas.width - dw) / 2 + drift
    const dy = (canvas.height - dh) / 2 - drift * 0.5
    ctx.fillStyle = '#000'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(img, dx, dy, dw, dh)
  }
  rec.start(500)
  const t0 = performance.now()
  await new Promise((resolve) => {
    const tick = () => {
      const p = Math.min(1, (performance.now() - t0) / (durationSec * 1000))
      draw(p)
      if (onProgress) onProgress(p)
      if (p < 1) requestAnimationFrame(tick)
      else resolve()
    }
    requestAnimationFrame(tick)
  })
  rec.stop()
  await stopped
  const blob = new Blob(chunks, { type: rec.mimeType || 'video/webm' })
  if (!blob.size) throw new Error('video khaali aayi')
  return blob
}

/* ---------- CapCut-style video editor (sab kuch phone pe, server pe kuch nahi jata) ---------- */
export default function VideoEditor({ api, onSendMessage, onGoToChat }) {
  const videoRef = useRef(null)
  const fileInputRef = useRef(null)
  const timelineRef = useRef(null)
  const audioRef = useRef(null)

  const [file, setFile] = useState(null)
  const [videoUrl, setVideoUrl] = useState(null)
  const [duration, setDuration] = useState(0)
  const [currentTime, setCurrentTime] = useState(0)
  const [playing, setPlaying] = useState(false)
  // Kept ranges — trim = pehle hisse ki shuruaat + aakhri hisse ka ant; cut se hisse bante hain
  const [segments, setSegments] = useState([])
  const [speed, setSpeed] = useState(1)
  const [muted, setMuted] = useState(false)
  const [brightness, setBrightness] = useState(100)
  const [contrast, setContrast] = useState(100)
  const [saturation, setSaturation] = useState(100)
  const [text, setText] = useState('')
  const [textPos, setTextPos] = useState('bottom') // top | center | bottom
  const [textSize, setTextSize] = useState(32)
  const [status, setStatus] = useState('')
  const [exporting, setExporting] = useState(false)
  const [asking, setAsking] = useState(false)
  const [sepia, setSepia] = useState(0)
  const [grayscale, setGrayscale] = useState(0)
  const [blurPx, setBlurPx] = useState(0)
  const [hueRotate, setHueRotate] = useState(0)
  const [genPrompt, setGenPrompt] = useState('')
  const [generating, setGenerating] = useState(false)
  const [editPrompt, setEditPrompt] = useState('')
  const [editBusy, setEditBusy] = useState(false)

  const trimStart = segments.length ? segments[0].start : 0
  const trimEnd = segments.length ? segments[segments.length - 1].end : 0
  const keptTotal = segments.reduce((a, s) => a + (s.end - s.start), 0)
  const filterString = () => `brightness(${brightness}%) contrast(${contrast}%) saturate(${saturation}%) sepia(${sepia}%) grayscale(${grayscale}%) hue-rotate(${hueRotate}deg) blur(${blurPx}px)`

  function resetFilters() {
    setBrightness(100)
    setContrast(100)
    setSaturation(100)
    setSepia(0)
    setGrayscale(0)
    setBlurPx(0)
    setHueRotate(0)
  }

  // Kisi video file/blob ko editor me load karo (upload, AI clip ya photo-clip — sab ek jaisa)
  function loadClipFile(f, { text: overlayText = '', textSize: size = 32 } = {}) {
    if (videoUrl) URL.revokeObjectURL(videoUrl)
    const url = URL.createObjectURL(f)
    setFile(f)
    setVideoUrl(url)
    setSegments([])
    setDuration(0)
    setCurrentTime(0)
    resetFilters()
    setSpeed(1)
    setMuted(false)
    setTextPos('bottom')
    setTextSize(size)
    setText(overlayText)
    setStatus('')
  }

  // Purana blob URL band karo (memory leak na ho)
  useEffect(() => () => { if (videoUrl) URL.revokeObjectURL(videoUrl) }, [videoUrl])

  async function onPickFile(e) {
    const f = e.target.files && e.target.files[0]
    e.target.value = ''
    if (!f) return
    if (f.type.startsWith('image/')) {
      // Photo ko 6 second ka still clip banao, phir editor me kholo
      if (generating) return
      setGenerating(true)
      setStatus('Photo ko video bana raha hai...')
      try {
        const imgUrl = URL.createObjectURL(f)
        const img = await loadImage(imgUrl)
        URL.revokeObjectURL(imgUrl)
        const blob = await imageToClip(img, { kenBurns: false, onProgress: (p) => setStatus(`Photo ko video bana raha hai... ${Math.round(p * 100)}%`) })
        loadClipFile(new File([blob], 'photo-clip.webm', { type: 'video/webm' }), { text: '' })
        setStatus('✅ Photo se 6 second ka clip ban gaya — ab edit kar sakte ho.')
      } catch (err) {
        setStatus('Photo se video nahi ban paya — Chrome use karke dobara try karo.')
      } finally {
        setGenerating(false)
      }
      return
    }
    if (!f.type.startsWith('video/')) {
      setStatus('Ye video ya photo file nahi hai — video ya photo chuno.')
      return
    }
    loadClipFile(f, { text: '' })
  }

  /* ---------- Feature 1: prompt se video banao (AI photo + motion + text) ---------- */
  async function generateVideoFromPrompt() {
    const prompt = genPrompt.trim()
    if (!prompt) {
      setStatus('Pehle prompt likho — jaise "sunset pe samundar kinare ghoda daud raha hai".')
      return
    }
    if (generating) return
    setGenerating(true)
    setStatus('AI photo bana raha hai...')
    try {
      const url = `https://image.pollinations.ai/prompt/${encodeURIComponent(prompt)}?width=720&height=1280&nologo=true`
      const res = await fetch(url)
      if (!res.ok) throw new Error('photo fetch failed')
      const blob = await res.blob()
      if (!blob.size || !String(blob.type || '').startsWith('image/')) throw new Error('photo nahi mili')
      const imgUrl = URL.createObjectURL(blob)
      const img = await loadImage(imgUrl)
      URL.revokeObjectURL(imgUrl)
      setStatus('AI video bana raha hai... 0%')
      const clip = await imageToClip(img, { kenBurns: true, onProgress: (p) => setStatus(`AI video bana raha hai... ${Math.round(p * 100)}%`) })
      loadClipFile(new File([clip], 'ai-video.webm', { type: 'video/webm' }), { text: prompt, textSize: 40 })
      setStatus('✅ AI video ready — ab trim/text/filter karke export karo.')
    } catch (err) {
      setStatus('Photo nahi ban payi — dobara try karo.')
    } finally {
      setGenerating(false)
    }
  }

  /* ---------- Feature 2: prompt se photo edit karo (keyword → client-side edit) ----------
     Jo keyword mile wo turant lagta hai; baaki RAMA chat me batata hai.
     Kabhi jhootha "lag gaya" nahi dikhate. */
  function applyEditPrompt(prompt) {
    const p = prompt.toLowerCase()
    const applied = []
    const textMatch = prompt.match(/^\s*(text|likho)\s+(.+)$/i)
    if (textMatch) {
      setText(textMatch[2].trim())
      applied.push(`text "${textMatch[2].trim()}"`)
    }
    if (/(sunset|warm|golden|shaam|sunehri)/.test(p)) {
      setBrightness(105)
      setContrast(115)
      setSaturation(130)
      setSepia(25)
      applied.push('Sunset (warm) filter')
    }
    if (/(black and white|black & white|\bbw\b|kaala safed|kala safed)/.test(p)) {
      setGrayscale(100)
      applied.push('Black & White filter')
    }
    if (/(bright|ujala|roshan|chamak)/.test(p)) {
      setBrightness(135)
      applied.push('Brightness up')
    }
    if (/(dark|moody|andhera)/.test(p)) {
      setBrightness(75)
      setContrast(120)
      applied.push('Dark/Moody filter')
    }
    if (/(blur|dhundhla)/.test(p)) {
      setBlurPx(3)
      applied.push('Blur')
    }
    if (/(vintage|old|purana)/.test(p)) {
      setSepia(60)
      setSaturation(70)
      setContrast(105)
      applied.push('Vintage filter')
    }
    return applied
  }

  function submitEditPrompt() {
    const prompt = editPrompt.trim()
    if (!prompt) {
      setStatus('Pehle edit prompt likho — jaise "sunset filter" ya "text Mera Video".')
      return
    }
    if (!file) {
      setStatus('Pehle video ya photo upload karo — phir prompt se edit kar sakte ho.')
      return
    }
    if (editBusy) return
    setEditBusy(true)
    const applied = applyEditPrompt(prompt)
    if (applied.length) {
      setStatus(`✅ ${applied.join(' + ')} lagaya.`)
    } else {
      setStatus('Is prompt ka direct edit nahi mila — RAMA ne chat me bataya hai, wahan se manually lagao.')
    }
    onSendMessage(`Photo/video edit prompt: "${prompt}". Maine abhi ye edit lagaya: ${applied.length ? applied.join(', ') : 'koi direct edit nahi mila'}. Is photo/video ko aur kaise behtar edit karun — filter, text, trim? Batao.`)
    setEditBusy(false)
    onGoToChat()
  }

  function onLoadedMetadata() {
    const v = videoRef.current
    if (!v) return
    const d = v.duration || 0
    setDuration(d)
    setSegments(d > 0 ? [{ start: 0, end: d }] : [])
  }

  // Delete kiye hue hisso ko playback me skip karo
  function onTimeUpdate() {
    const v = videoRef.current
    if (!v) return
    const t = v.currentTime
    setCurrentTime(t)
    if (v.paused || !segments.length) return
    const inside = segments.some((s) => t >= s.start && t < s.end - 0.02)
    if (inside) return
    const next = segments.find((s) => s.start > t)
    if (next) v.currentTime = next.start
    else {
      v.pause()
      v.currentTime = segments[0].start
    }
  }

  function togglePlay() {
    const v = videoRef.current
    if (!v) return
    if (v.paused) {
      const t = v.currentTime
      const inside = segments.some((s) => t >= s.start && t < s.end - 0.05)
      if (!inside) {
        const next = segments.find((s) => s.start > t) || segments[0]
        if (next) v.currentTime = next.start
      }
      v.playbackRate = speed
      v.play().catch(() => {})
    } else {
      v.pause()
    }
  }

  function seekTo(t) {
    const v = videoRef.current
    if (!v || !duration) return
    v.currentTime = Math.max(0, Math.min(duration, t))
  }

  function onTimelineClick(e) {
    const tl = timelineRef.current
    if (!tl || !duration) return
    const rect = tl.getBoundingClientRect()
    const t = ((e.clientX - rect.left) / rect.width) * duration
    seekTo(t)
  }

  function setTrimEdge(which, t) {
    if (!segments.length) return
    const segs = segments.map((s) => ({ ...s }))
    if (which === 'start') {
      segs[0].start = Math.max(0, Math.min(t, segs[0].end - 0.1))
    } else {
      const last = segs.length - 1
      segs[last].end = Math.min(duration, Math.max(t, segs[last].start + 0.1))
    }
    setSegments(segs)
  }

  function dragEdge(which, e) {
    if (!e.buttons) return
    const tl = timelineRef.current
    if (!tl || !duration) return
    const rect = tl.getBoundingClientRect()
    const t = ((e.clientX - rect.left) / rect.width) * duration
    setTrimEdge(which, t)
  }

  function cutAtPlayhead() {
    const t = currentTime
    const idx = segments.findIndex((s) => t > s.start + 0.1 && t < s.end - 0.1)
    if (idx < 0) {
      setStatus('Kaante ke liye playhead ko kisi hisse ke beech me rakho.')
      return
    }
    const seg = segments[idx]
    const next = [...segments]
    next.splice(idx, 1, { start: seg.start, end: t }, { start: t, end: seg.end })
    setSegments(next)
    setStatus('✂️ Kaat diya — ab do hisse hain. Kisi hisse ko 🗑 se delete kar sakte ho.')
  }

  function deleteSegment(i) {
    if (segments.length <= 1) {
      setStatus('Aakhri hissa delete nahi kar sakte.')
      return
    }
    setSegments(segments.filter((_, j) => j !== i))
    setStatus('Hissa delete kar diya.')
  }

  function changeSpeed(s) {
    setSpeed(s)
    if (videoRef.current) videoRef.current.playbackRate = s
  }

  function toggleMute() {
    const next = !muted
    setMuted(next)
    if (videoRef.current) videoRef.current.muted = next
  }

  // Video ki awaaz ko ek baar AudioContext se jodo (dobara export pe dobara nahi ban sakta)
  function getAudioStream(video) {
    if (audioRef.current) return audioRef.current.dest.stream
    const AC = window.AudioContext || window.webkitAudioContext
    if (!AC) throw new Error('audio nahi hai')
    const ctx = new AC()
    if (ctx.state === 'suspended') ctx.resume().catch(() => {})
    const src = ctx.createMediaElementSource(video)
    const dest = ctx.createMediaStreamDestination()
    src.connect(dest)
    src.connect(ctx.destination)
    audioRef.current = { ctx, dest }
    return dest.stream
  }

  async function exportVideo() {
    if (!file || exporting) return
    if (!segments.length) {
      setStatus('Koi hissa nahi bacha — video dobara load karo.')
      return
    }
    const probe = document.createElement('canvas')
    const hasCapture = typeof probe.captureStream === 'function'
    if (!hasCapture || !window.MediaRecorder) {
      // Fallback: original video ka trimmed hissa (time ke hisaab se bytes kaat ke)
      const startByte = Math.floor((file.size * trimStart) / duration)
      const endByte = Math.max(startByte + 1, Math.floor((file.size * trimEnd) / duration))
      const slice = file.slice(startByte, endByte, file.type)
      const url = URL.createObjectURL(slice)
      const ext = (file.name.split('.').pop() || 'mp4').toLowerCase()
      const base = file.name.replace(/\.[^.]+$/, '') || 'video'
      triggerDownload(url, `${base}-trim.${ext}`)
      setStatus('⚠️ Is browser me video recording nahi hai — original video ka trimmed hissa download kiya hai. Ye file kuch players me nahi chalegi; poora export ke liye Chrome use karo.')
      return
    }
    const v = videoRef.current
    if (!v) return
    setExporting(true)
    setStatus('Export ho raha hai... 0%')
    let audioLost = false
    try {
      const canvas = document.createElement('canvas')
      const scale = Math.min(1, 1280 / (v.videoWidth || 1280))
      canvas.width = Math.max(2, Math.round((v.videoWidth || 640) * scale))
      canvas.height = Math.max(2, Math.round((v.videoHeight || 360) * scale))
      const ctx = canvas.getContext('2d')
      const vStream = canvas.captureStream(30)
      const tracks = [...vStream.getVideoTracks()]
      if (!muted) {
        try {
          const aStream = getAudioStream(v)
          tracks.push(...aStream.getAudioTracks())
        } catch (e) {
          audioLost = true
        }
      }
      const stream = new MediaStream(tracks)
      const mime = ['video/webm;codecs=vp9,opus', 'video/webm;codecs=vp8,opus', 'video/webm'].find((m) => {
        try { return window.MediaRecorder.isTypeSupported(m) } catch (e) { return false }
      })
      const recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream)
      const chunks = []
      recorder.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data) }
      const stopped = new Promise((resolve) => { recorder.onstop = resolve })
      let recording = true
      const draw = () => {
        if (!recording) return
        if (v.readyState >= 2) {
          ctx.filter = filterString()
          ctx.drawImage(v, 0, 0, canvas.width, canvas.height)
          ctx.filter = 'none'
          if (text.trim()) {
            drawTextOnCanvas(ctx, canvas, text, textPos, textSize, canvas.width / (v.clientWidth || canvas.width))
          }
        }
        requestAnimationFrame(draw)
      }
      requestAnimationFrame(draw)
      recorder.start(500)
      let done = 0
      for (let i = 0; i < segments.length; i++) {
        const seg = segments[i]
        await seekToTime(v, seg.start)
        v.playbackRate = speed
        try {
          await v.play()
        } catch (e) {
          v.muted = true
          audioLost = true
          await v.play()
        }
        const endT = seg.end - 0.05
        let lastT = -1
        let stall = 0
        while (v.currentTime < endT && !v.paused && !v.ended) {
          await new Promise((r) => setTimeout(r, 100))
          if (Math.abs(v.currentTime - lastT) < 0.01) stall++
          else { stall = 0; lastT = v.currentTime }
          if (stall > 50) break // 5 second se aage nahi badh raha — atak gaya
          const pct = Math.round(((done + Math.min(Math.max(v.currentTime - seg.start, 0), seg.end - seg.start)) / keptTotal) * 100)
          setStatus(`Export ho raha hai... ${pct}%`)
        }
        v.pause()
        done += seg.end - seg.start
      }
      recording = false
      recorder.stop()
      await stopped
      const blob = new Blob(chunks, { type: recorder.mimeType || 'video/webm' })
      if (!blob.size) throw new Error('recording khaali aayi')
      const url = URL.createObjectURL(blob)
      triggerDownload(url, 'rama-edit.webm')
      setStatus('✅ Export ho gaya — rama-edit.webm download ho gaya.' + (audioLost ? ' (Is export me audio nahi aaya.)' : ''))
    } catch (e) {
      setStatus('Export nahi ho paya — ' + (e && e.message ? e.message : 'dobara try karo.'))
    } finally {
      setExporting(false)
      if (v) {
        try { v.pause() } catch (e) { /* ignore */ }
        v.muted = muted
        v.playbackRate = speed
        v.currentTime = segments.length ? segments[0].start : 0
      }
    }
  }

  /* ---------- Part B: video ka frame RAMA ko bhejo, wo bataye kaise edit karein ---------- */
  async function askRama() {
    if (!file || !videoRef.current) {
      setStatus('Pehle video upload karo — phir RAMA se poochh sakte ho.')
      return
    }
    if (asking) return
    setAsking(true)
    setStatus('Video ka frame RAMA ko bhej rahe hain...')
    const v = videoRef.current
    const prevTime = v.currentTime
    try {
      v.pause()
      const mid = (trimStart + trimEnd) / 2
      await seekToTime(v, mid)
      const cw = Math.min(v.videoWidth || 640, 640)
      const ch = Math.max(2, Math.round((cw * (v.videoHeight || 360)) / (v.videoWidth || 640)))
      const canvas = document.createElement('canvas')
      canvas.width = cw
      canvas.height = ch
      canvas.getContext('2d').drawImage(v, 0, 0, cw, ch)
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'))
      if (!blob) throw new Error('frame nahi bana')
      const frameFile = new File([blob], 'rama-video-frame.png', { type: 'image/png' })
      const form = new FormData()
      form.append('file', frameFile)
      const res = await fetch(`${api}/upload`, { method: 'POST', body: form })
      if (!res.ok) throw new Error('upload failed')
      const data = await res.json()
      const desc = data && typeof data.description === 'string' ? data.description.trim() : ''
      if (!desc) throw new Error('no description')
      onSendMessage(`Maine ek video bheji hai. RAMA ne usme ye dekha: ${desc}. Is video ko kaise edit karun — kya trim karun, kya text add karun, kya filter lagau? Batao.`)
      onGoToChat()
    } catch (e) {
      setStatus('Video RAMA ko nahi bhej paya — dobara try karo.')
    } finally {
      setAsking(false)
      try { v.currentTime = prevTime } catch (e) { /* ignore */ }
    }
  }

  return (
    <div className="tab-view video-editor">
      <h2 className="tab-title">🎬 Video Editor</h2>

      <div className="ve-section">
        <h3>🎬 Prompt se video banao</h3>
        <input className="ve-text-input" type="text" placeholder="Prompt likho — jaise 'sunset pe samundar kinare ghoda daud raha hai'" value={genPrompt} onChange={(e) => setGenPrompt(e.target.value)} />
        <button className="ve-export-btn" onClick={generateVideoFromPrompt} disabled={generating}>
          {generating ? 'Bana raha hai...' : '🎬 Video banao'}
        </button>
        <p className="ve-note">AI photo + motion video — Ye AI photo ko motion + text dekar video banata hai. (Asli AI motion video nahi — photo pe slow zoom + prompt ka text.)</p>
      </div>

      {!file && (
        <div className="ve-section">
          <p className="ve-note">Video chuno aur CapCut style me edit karo — trim, cut, text, speed, filter. Video sirf is phone me edit hoti hai, server pe upload nahi hoti. Photo bhi chuna sakte ho — wo 6 second ka clip ban jayegi.</p>
          <button className="ve-export-btn" onClick={() => fileInputRef.current && fileInputRef.current.click()}>📹 Video ya photo chuno</button>
        </div>
      )}

      <input ref={fileInputRef} type="file" accept="video/*,image/*" style={{ display: 'none' }} onChange={onPickFile} />

      {file && (
        <>
          <div className="ve-preview-wrap">
            <video
              ref={videoRef}
              src={videoUrl}
              playsInline
              preload="metadata"
              style={{ filter: filterString() }}
              onLoadedMetadata={onLoadedMetadata}
              onTimeUpdate={onTimeUpdate}
              onPlay={() => setPlaying(true)}
              onPause={() => setPlaying(false)}
              onEnded={() => setPlaying(false)}
              muted={muted}
            />
            {text.trim() && (
              <div className={`ve-text-overlay pos-${textPos}`} style={{ fontSize: `${textSize}px` }}>{text}</div>
            )}
          </div>

          <div className="ve-play-row">
            <button className="ve-play-btn" onClick={togglePlay} aria-label="Play ya Pause">{playing ? '⏸' : '▶'}</button>
            <span className="ve-time">{fmt(currentTime)} / {fmt(duration)}</span>
            <span className="ve-time">• Bacha: {fmt(keptTotal)} ({segments.length} hisse)</span>
            <button className="ve-btn" style={{ marginLeft: 'auto' }} onClick={() => fileInputRef.current && fileInputRef.current.click()}>🔄 Dusri video</button>
          </div>

          <div className="ve-section">
            <h3>Timeline — tap karke seek karo</h3>
            <div className="ve-timeline" ref={timelineRef} onClick={onTimelineClick}>
              {segments.map((s, i) => (
                <div
                  key={i}
                  className="ve-seg"
                  style={{ left: `${(s.start / duration) * 100}%`, width: `${((s.end - s.start) / duration) * 100}%` }}
                />
              ))}
              <div className="ve-playhead" style={{ left: `${(currentTime / duration) * 100}%` }} />
              <div
                className="ve-handle left"
                style={{ left: `calc(${(trimStart / duration) * 100}% - 8px)` }}
                onPointerDown={(e) => { e.preventDefault(); e.stopPropagation(); e.currentTarget.setPointerCapture(e.pointerId) }}
                onPointerMove={(e) => dragEdge('start', e)}
                onClick={(e) => e.stopPropagation()}
              >❰</div>
              <div
                className="ve-handle right"
                style={{ left: `calc(${(trimEnd / duration) * 100}% - 8px)` }}
                onPointerDown={(e) => { e.preventDefault(); e.stopPropagation(); e.currentTarget.setPointerCapture(e.pointerId) }}
                onPointerMove={(e) => dragEdge('end', e)}
                onClick={(e) => e.stopPropagation()}
              >❱</div>
            </div>
            <div className="ve-slider-row">
              <label>Start: {fmt(trimStart)}</label>
              <input type="range" min={0} max={duration} step={0.1} value={trimStart} onChange={(e) => setTrimEdge('start', Number(e.target.value))} disabled={!duration} />
            </div>
            <div className="ve-slider-row">
              <label>End: {fmt(trimEnd)}</label>
              <input type="range" min={0} max={duration} step={0.1} value={trimEnd} onChange={(e) => setTrimEdge('end', Number(e.target.value))} disabled={!duration} />
            </div>
            <div className="ve-seg-list">
              {segments.map((s, i) => (
                <div key={i} className="ve-seg-item">
                  <span>Hissa {i + 1}: {fmt(s.start)} – {fmt(s.end)}</span>
                  <button className="ve-seg-del" onClick={() => deleteSegment(i)} aria-label="Hissa delete karo">🗑</button>
                </div>
              ))}
            </div>
            <button className="ve-btn" onClick={cutAtPlayhead}>✂️ Yahan se kaato (playhead)</button>
          </div>

          <div className="ve-section">
            <h3>Speed aur Sound</h3>
            <div className="ve-btn-row">
              {SPEEDS.map((s) => (
                <button key={s} className={`ve-btn ${speed === s ? 'active' : ''}`} onClick={() => changeSpeed(s)}>{s}x</button>
              ))}
              <button className="ve-btn" onClick={toggleMute}>{muted ? '🔇 Muted' : '🔊 Sound on'}</button>
            </div>
          </div>

          <div className="ve-section">
            <h3>Filter</h3>
            <div className="ve-slider-row">
              <label>Brightness: {brightness}%</label>
              <input type="range" min={50} max={150} value={brightness} onChange={(e) => setBrightness(Number(e.target.value))} />
            </div>
            <div className="ve-slider-row">
              <label>Contrast: {contrast}%</label>
              <input type="range" min={50} max={150} value={contrast} onChange={(e) => setContrast(Number(e.target.value))} />
            </div>
            <div className="ve-slider-row">
              <label>Saturation: {saturation}%</label>
              <input type="range" min={0} max={200} value={saturation} onChange={(e) => setSaturation(Number(e.target.value))} />
            </div>
            <button className="ve-btn" onClick={resetFilters}>Filter reset karo</button>
          </div>

          <div className="ve-section">
            <h3>Text Overlay</h3>
            <input className="ve-text-input" type="text" placeholder="Text likho — jaise 'Mera Video'" value={text} onChange={(e) => setText(e.target.value)} />
            <div className="ve-btn-row">
              {['top', 'center', 'bottom'].map((p) => (
                <button key={p} className={`ve-btn ${textPos === p ? 'active' : ''}`} onClick={() => setTextPos(p)}>
                  {p === 'top' ? '⬆ Upar' : p === 'center' ? '◉ Beech' : '⬇ Neeche'}
                </button>
              ))}
            </div>
            <div className="ve-slider-row">
              <label>Size: {textSize}px</label>
              <input type="range" min={16} max={72} value={textSize} onChange={(e) => setTextSize(Number(e.target.value))} />
            </div>
            {text && <button className="ve-btn" onClick={() => setText('')}>Text hatao</button>}
          </div>

          <div className="ve-section">
            <h3>✨ Prompt se photo edit karo</h3>
            <input className="ve-text-input" type="text" placeholder="Jaise: sunset filter, black and white, text Mera Video" value={editPrompt} onChange={(e) => setEditPrompt(e.target.value)} />
            <button className="ve-ask-btn" onClick={submitEditPrompt} disabled={editBusy}>
              {editBusy ? 'Edit kar rahe hain...' : '✨ Edit karo'}
            </button>
            <p className="ve-note">RAMA ko bhi bhejta hai — wo chat me aur idea dega. Background change / object add jaisa asli AI pixel-edit yahan nahi hota; filter, brightness, blur aur text hi lag sakta hai.</p>
          </div>

          <button className="ve-export-btn" onClick={exportVideo} disabled={exporting || !segments.length}>
            {exporting ? 'Export ho raha hai...' : '⬇ Export karo (.webm)'}
          </button>
          <button className="ve-ask-btn" onClick={askRama} disabled={asking}>
            {asking ? 'RAMA ko bhej rahe hain...' : '💬 RAMA se poochho — is video ko kaise edit karun?'}
          </button>
          <p className="ve-note">RAMA se poochho: video ka beech wala frame RAMA ko bheja jata hai, wo dekh kar batayega kya trim karein, kya text add karein.</p>
          {status && <div className="ve-status">{status}</div>}
        </>
      )}

      {status && !file && <div className="ve-status">{status}</div>}
    </div>
  )
}
