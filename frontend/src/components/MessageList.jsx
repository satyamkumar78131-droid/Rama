import { useEffect, useRef, useState } from 'react'

/* 🔊 sunao / 📋 copy / 👍 like — har AI jawab ke neeche */
function Actions({ text }) {
  const [liked, setLiked] = useState(false)
  const [copied, setCopied] = useState(false)

  function speak() {
    try {
      if (!('speechSynthesis' in window)) return
      window.speechSynthesis.cancel()
      window.speechSynthesis.speak(new SpeechSynthesisUtterance(text))
    } catch (e) {
      /* voice na chale to chup-chaap rehne do */
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
    } catch (e) {
      const ta = document.createElement('textarea')
      ta.value = text
      document.body.appendChild(ta)
      ta.select()
      try { document.execCommand('copy') } catch (_) {}
      document.body.removeChild(ta)
    }
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="actions">
      <button type="button" onClick={speak} title="Sunao">🔊</button>
      <button type="button" onClick={copy} title="Copy karo">{copied ? '✅' : '📋'}</button>
      <button
        type="button"
        onClick={() => setLiked(!liked)}
        title="Achha laga"
        className={liked ? 'liked' : ''}
      >
        👍
      </button>
    </div>
  )
}

export default function MessageList({ messages, typing }) {
  const bottomRef = useRef(null)

  /* Naya message ya typing aate hi neeche scroll karo —
     warna bheja hua message neeche chhup jata hai */
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, typing])

  return (
    <div className="messages">
      {messages.length === 0 && (
        <div className="empty">
          <img src="/rama-avatar.jpg" alt="Rama" className="home-avatar" />
          <div className="home-name">Rama</div>
          <h2>Namaste! Main Rama hoon.</h2>
          <p>Kuch bhi poochho — main madad karunga. 😊</p>
          <p className="muted">Tip: "yaad rakho mera favourite colour neela hai" likh ke dekho!</p>
        </div>
      )}
      {messages.map((m, i) => (
        <div key={i} className={`msg-row ${m.role === 'user' ? 'right' : 'left'}`}>
          <div className={`bubble ${m.role === 'user' ? 'user' : 'ai'}`}>
            {m.role === 'user' ? (
              <div className="bubble-label">You</div>
            ) : (
              <div className="responding">RAMA Responding</div>
            )}
            {m.image && <img src={m.image} alt="Photo" className="bubble-img" />}
            {m.content ? <div className="bubble-text">{m.content}</div> : null}
            {m.role === 'assistant' && <Actions text={m.content} />}
            {m.sources && m.sources.length > 0 && (
              <div className="sources">
                {m.sources.map((s, j) => (
                  <div key={j} className="source-line">
                    🔍 Source: <a href={s.url} target="_blank" rel="noreferrer">{s.source || s.title}</a>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      ))}
      {typing && (
        <div className="msg-row left">
          <div className="bubble ai typing">Rama likh raha hai...</div>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  )
}
