import { useEffect, useRef, useState } from 'react'
import MessageList from './components/MessageList.jsx'
import ChatInput from './components/ChatInput.jsx'
import Sidebar from './components/Sidebar.jsx'
import VideoEditor from './components/VideoEditor.jsx'

// Vercel pe VITE_API_BASE_URL set karo (Render backend URL), local me localhost:8000
const API = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const IDEAS = [
  'ek joke sunao',
  'Photosynthesis kya hai',
  'Taj Mahal kisne banaya',
  'yaad rakho mera naam Satya hai',
  'aaj ka mausam kaisa hai',
]

const TABS = [
  { id: 'chat', icon: '💬', label: 'Chat' },
  { id: 'video', icon: '🎬', label: 'Video' },
  { id: 'chats', icon: '📰', label: 'Chats' },
  { id: 'ideas', icon: '💡', label: 'Ideas' },
  { id: 'memory', icon: '☑', label: 'Memory' },
  { id: 'more', icon: '▦', label: 'More' },
]

function loadStored(key) {
  try { return localStorage.getItem(key) === '1' } catch (e) { return false }
}

function storeValue(key, value) {
  try { localStorage.setItem(key, value ? '1' : '0') } catch (e) { /* ignore */ }
}

export default function App() {
  const [messages, setMessages] = useState([])
  const [conversationId, setConversationId] = useState(null)
  const [conversations, setConversations] = useState([])
  const [memories, setMemories] = useState([])
  const [typing, setTyping] = useState(false)
  const [mode, setMode] = useState('fast') // fast | deep
  const [tab, setTab] = useState('chat') // chat | video | chats | ideas | memory | more
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [splash, setSplash] = useState(true) // SAIME-style startup animation, "RAMA" text
  const [splashLeaving, setSplashLeaving] = useState(false)
  const [voiceOn, setVoiceOn] = useState(() => loadStored('rama_voice'))
  const [wakeOn, setWakeOn] = useState(() => loadStored('rama_wakelock'))
  const [wakeSupported] = useState(() => {
    try { return 'wakeLock' in navigator } catch (e) { return false }
  })
  const wakeLockRef = useRef(null)
  const wakeOnRef = useRef(wakeOn)
  const spokenIdxRef = useRef(-1)

  useEffect(() => { wakeOnRef.current = wakeOn }, [wakeOn])

  async function loadSidebar() {
    try {
      const [cRes, mRes] = await Promise.all([
        fetch(`${API}/conversations`),
        fetch(`${API}/memories`),
      ])
      if (cRes.ok) setConversations(await cRes.json())
      if (mRes.ok) setMemories(await mRes.json())
    } catch (e) {
      // Backend band ho to sidebar khali rehta hai
    }
  }

  useEffect(() => { loadSidebar() }, [])

  /* ---------- Startup splash: dot rolls, "RAMA" letters ek-ek karke ---------- */
  function playSplashChime() {
    try {
      const AC = window.AudioContext || window.webkitAudioContext
      if (!AC) return
      const ctx = new AC()
      if (ctx.state === 'suspended') ctx.resume().catch(() => {})
      ;[523.25, 659.25, 783.99].forEach((f, i) => {
        const o = ctx.createOscillator()
        const g = ctx.createGain()
        o.type = 'sine'
        o.frequency.value = f
        const t = ctx.currentTime + 0.9 + i * 0.12
        g.gain.setValueAtTime(0.0001, t)
        g.gain.exponentialRampToValueAtTime(0.1, t + 0.02)
        g.gain.exponentialRampToValueAtTime(0.0001, t + 0.35)
        o.connect(g)
        g.connect(ctx.destination)
        o.start(t)
        o.stop(t + 0.4)
      })
      setTimeout(() => { try { ctx.close() } catch (e) {} }, 1800)
    } catch (e) {
      /* sound na baje to chup-chaap rehne do */
    }
  }

  useEffect(() => {
    playSplashChime()
    const t1 = setTimeout(() => setSplashLeaving(true), 2300)
    const t2 = setTimeout(() => setSplash(false), 2600)
    return () => { clearTimeout(t1); clearTimeout(t2) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /* ---------- AI Voice: jawab ko bol kar sunana ---------- */
  function speakText(text) {
    try {
      if (!('speechSynthesis' in window)) return
      window.speechSynthesis.cancel()
      const u = new SpeechSynthesisUtterance(text)
      u.rate = 1.0
      const voices = window.speechSynthesis.getVoices() || []
      const hi = voices.find((v) => v.lang && v.lang.toLowerCase().startsWith('hi'))
      if (hi) u.voice = hi
      window.speechSynthesis.speak(u)
    } catch (e) {
      /* voice na chale to chup-chaap rehne do */
    }
  }

  // Naya assistant jawab aate hi bol do (agar AI Voice ON hai)
  useEffect(() => {
    if (messages.length === 0) return
    const idx = messages.length - 1
    const last = messages[idx]
    if (last.role !== 'assistant' || idx <= spokenIdxRef.current) return
    spokenIdxRef.current = idx
    if (voiceOn && last.content) speakText(last.content)
  }, [messages, voiceOn])

  /* ---------- Wake Lock: screen on rakhna ---------- */
  async function requestWakeLock() {
    try {
      if (!('wakeLock' in navigator)) return
      wakeLockRef.current = await navigator.wakeLock.request('screen')
    } catch (e) {
      wakeLockRef.current = null
    }
  }

  function releaseWakeLock() {
    try {
      const lock = wakeLockRef.current
      wakeLockRef.current = null
      if (lock) {
        const p = lock.release()
        if (p && p.catch) p.catch(() => {})
      }
    } catch (e) { /* ignore */ }
  }

  useEffect(() => {
    if (wakeOn) requestWakeLock()
    else releaseWakeLock()
    function onVis() {
      if (document.visibilityState === 'visible' && wakeOnRef.current) requestWakeLock()
    }
    document.addEventListener('visibilitychange', onVis)
    return () => {
      document.removeEventListener('visibilitychange', onVis)
      releaseWakeLock()
    }
  }, [wakeOn])

  function toggleVoice() {
    const next = !voiceOn
    setVoiceOn(next)
    storeValue('rama_voice', next)
    if (!next) {
      try { window.speechSynthesis?.cancel() } catch (e) { /* ignore */ }
    }
  }

  function toggleWake() {
    if (!wakeSupported) return
    const next = !wakeOn
    setWakeOn(next)
    storeValue('rama_wakelock', next)
  }

  async function sendMessage(text) {
    // Naya message bhejte hi bolna band karo
    try { window.speechSynthesis?.cancel() } catch (e) { /* ignore */ }
    const userMsg = { role: 'user', content: text }
    setMessages((prev) => [...prev, userMsg])
    setTyping(true)
    try {
      // Render free tier kabhi-kabhi ek request drop kar deta hai — ek baar 2s ruk ke dobara try karo
      let res, data
      for (let attempt = 0; attempt < 2; attempt++) {
        try {
          res = await fetch(`${API}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, conversation_id: conversationId, mode }),
          })
          data = await res.json()
          break
        } catch (e) {
          if (attempt === 0) await new Promise((r) => setTimeout(r, 2000))
          else throw e
        }
      }
      if (res.ok) {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: data.answer, sources: data.sources || [] },
        ])
        if (data.conversation_id) setConversationId(data.conversation_id)
        loadSidebar()
      } else {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: 'Error: ' + (data.detail || 'kuch galat hua') },
        ])
      }
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: 'Backend se connect nahi ho pa raha. Backend ek second ke liye band ho gaya tha — wahi message dobara bhejo, ab chal raha hoga.',
        },
      ])
    } finally {
      setTyping(false)
    }
  }

  /* ---------- Pic / file upload: POST {API}/upload, field "file" ----------
     Backend contract: {filename, chars, description?}
     description sirf images ke liye hoti hai (photo ka Gemini description). */
  async function handleFile(file) {
    if (!file) return
    const isImage = (file.type || '').startsWith('image/')
    let imageDataUrl = null
    if (isImage) {
      imageDataUrl = await new Promise((resolve) => {
        const reader = new FileReader()
        reader.onload = () => resolve(reader.result)
        reader.onerror = () => resolve(null)
        reader.readAsDataURL(file)
      })
    }
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: isImage ? '' : `📄 ${file.name}`, image: imageDataUrl },
    ])
    setTab('chat')
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await fetch(`${API}/upload`, { method: 'POST', body: form })
      if (!res.ok) throw new Error('upload failed')
      const data = await res.json()
      const ext = (file.name.split('.').pop() || '').toLowerCase()
      let reply
      if (ext === 'pdf') {
        reply = (data && typeof data.message === 'string' && data.message.trim())
          ? data.message
          : 'PDF abhi supported nahi hai — .txt me convert karke bhejo.'
      } else if (isImage) {
        reply = (data && typeof data.description === 'string' && data.description.trim())
          ? data.description
          : 'Photo mil gayi, par isko dekh nahi paya — dobara try karo.'
      } else {
        reply = `✅ ${data.filename || file.name} save ho gayi (${data.chars} characters) — iske baare me kuch bhi poochho.`
      }
      setMessages((prev) => [...prev, { role: 'assistant', content: reply }])
      loadSidebar()
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: 'Upload nahi ho paya — dobara try karo.' },
      ])
    }
  }

  function newChat() {
    setMessages([])
    setConversationId(null)
    spokenIdxRef.current = -1
  }

  function selectChat(id) {
    // Simple version: purani chat select karne pe uska context set hota hai
    setConversationId(id)
    setMessages([])
    spokenIdxRef.current = -1
  }

  function handleNewChat() {
    newChat()
    setDrawerOpen(false)
    setTab('chat')
  }

  function handleSelectChat(id) {
    selectChat(id)
    setDrawerOpen(false)
    setTab('chat')
  }

  function sendIdea(text) {
    setTab('chat')
    sendMessage(text)
  }

  const hasHistory = conversations.length > 0 || memories.length > 0

  return (
    <div className="app">
      {splash && (
        <div className={`splash ${splashLeaving ? 'leaving' : ''}`} onClick={() => setSplash(false)}>
          <div className="splash-top-dots"><span /><span /><span /></div>
          <div className="splash-word">
            <span className="splash-dot" />
            <span className="splash-letter" style={{ animationDelay: '0.35s' }}>R</span>
            <span className="splash-letter" style={{ animationDelay: '0.55s' }}>A</span>
            <span className="splash-letter" style={{ animationDelay: '0.75s' }}>M</span>
            <span className="splash-letter" style={{ animationDelay: '0.95s' }}>A</span>
          </div>
          <div className="splash-sub">Satya ka AI assistant</div>
        </div>
      )}
      <header className="top-bar">
        <button className="hamburger" onClick={() => setDrawerOpen(true)} aria-label="Menu">
          ☰
          {hasHistory && <span className="ham-dot" />}
        </button>
      </header>

      <main className="chat">
        {tab === 'chat' && (
          <>
            <MessageList messages={messages} typing={typing} />
            <ChatInput onSend={sendMessage} sending={typing} onFile={handleFile} />
          </>
        )}

        {tab === 'video' && (
          <VideoEditor api={API} onSendMessage={sendMessage} onGoToChat={() => setTab('chat')} />
        )}

        {tab === 'chats' && (
          <div className="tab-view">
            <h2 className="tab-title">Chats</h2>
            {conversations.length === 0 && <p className="muted">Abhi koi chat nahi</p>}
            {conversations.map((c) => (
              <button key={c.id} className="list-item" onClick={() => handleSelectChat(c.id)}>
                {c.title}
              </button>
            ))}
          </div>
        )}

        {tab === 'ideas' && (
          <div className="tab-view">
            <h2 className="tab-title">Ideas</h2>
            <p className="muted">Kuch try karo:</p>
            <div className="chips">
              {IDEAS.map((s) => (
                <button key={s} className="chip" onClick={() => sendIdea(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {tab === 'memory' && (
          <div className="tab-view">
            <h2 className="tab-title">Memory</h2>
            {memories.length === 0 && <p className="muted">Koi yaad nahi — "yaad rakho ..." likho</p>}
            {memories.map((m) => (
              <div key={m.id} className="memory-item">
                <b>{m.key}:</b> {m.value}
              </div>
            ))}
          </div>
        )}

        {tab === 'more' && (
          <div className="tab-view">
            <h2 className="tab-title">More</h2>
            <button className="wide-btn" onClick={handleNewChat}>+ New chat</button>
            <div className="setting-row">
              <span className="setting-label">Mode</span>
              <span className="mode-toggle">
                <button
                  className={mode === 'fast' ? 'mode-btn active' : 'mode-btn'}
                  onClick={() => setMode('fast')}
                >
                  ⚡ Fast
                </button>
                <button
                  className={mode === 'deep' ? 'mode-btn active' : 'mode-btn'}
                  onClick={() => setMode('deep')}
                >
                  🧠 Deep
                </button>
              </span>
            </div>
            <div className="setting-row">
              <span className="setting-label">AI Voice <small>— jawab khud bol kar sunaye</small></span>
              <button
                className={`switch ${voiceOn ? 'on' : ''}`}
                onClick={toggleVoice}
                role="switch"
                aria-checked={voiceOn}
                aria-label="AI Voice"
              >
                <span className="knob" />
              </button>
            </div>
            <div className="setting-row">
              <span className="setting-label">Wake Lock <small>— screen on rakhe</small></span>
              <button
                className={`switch ${wakeOn ? 'on' : ''}`}
                onClick={toggleWake}
                disabled={!wakeSupported}
                role="switch"
                aria-checked={wakeOn}
                aria-label="Wake Lock"
              >
                <span className="knob" />
              </button>
            </div>
            {!wakeSupported && <p className="muted">Is browser me screen-on lock nahi hai</p>}
            <p className="about">RAMA — Satya ka AI assistant. Brain: Qwen + Gemini.</p>
          </div>
        )}
      </main>

      <nav className="bottom-nav">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={`nav-item ${tab === t.id ? 'active' : ''}`}
            onClick={() => setTab(t.id)}
          >
            <span className="nav-icon">{t.icon}</span>
            <span className="nav-label">{t.label}</span>
          </button>
        ))}
      </nav>

      <div
        className={`drawer-backdrop ${drawerOpen ? 'open' : ''}`}
        onClick={() => setDrawerOpen(false)}
        aria-hidden={!drawerOpen}
      >
        <div className="drawer" onClick={(e) => e.stopPropagation()}>
          <button className="drawer-close" onClick={() => setDrawerOpen(false)} aria-label="Band karo">✕</button>
          <Sidebar
            conversations={conversations}
            memories={memories}
            onNewChat={handleNewChat}
            onSelectChat={handleSelectChat}
            activeId={conversationId}
          />
        </div>
      </div>
    </div>
  )
}
