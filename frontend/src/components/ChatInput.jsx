import { useRef, useState } from 'react'

/* sending=true hone par bhi input khula rehta hai — type karte hue text dikhta hai,
   sirf Send button band hota hai jab tak Rama jawab likh raha ho.
   Input khali ho to 🎤 mic dikhta hai, text hote hi ➤ send button. */
export default function ChatInput({ onSend, sending, onFile }) {
  const [text, setText] = useState('')
  const [listening, setListening] = useState(false)
  const [placeholder, setPlaceholder] = useState('Rama se kuch poochho...')
  const fileRef = useRef(null)
  const recRef = useRef(null)

  function submit(e) {
    e.preventDefault()
    const value = text.trim()
    if (!value || sending) return
    onSend(value)
    setText('')
  }

  function pickFile() {
    fileRef.current?.click()
  }

  function onFileChange(e) {
    const f = e.target.files && e.target.files[0]
    e.target.value = ''
    if (f && onFile) onFile(f)
  }

  function stopListening() {
    try { recRef.current?.stop() } catch (err) { /* ignore */ }
    recRef.current = null
    setListening(false)
  }

  function toggleMic() {
    if (listening) {
      stopListening()
      return
    }
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) {
      setPlaceholder('Is browser me voice typing nahi hai')
      setTimeout(() => setPlaceholder('Rama se kuch poochho...'), 2000)
      return
    }
    try {
      const rec = new SR()
      rec.lang = 'hi-IN'
      rec.interimResults = true
      rec.continuous = false
      const base = text
      let finalText = ''
      rec.onresult = (ev) => {
        let interim = ''
        for (let i = ev.resultIndex; i < ev.results.length; i++) {
          const r = ev.results[i]
          if (r.isFinal) finalText += r[0].transcript
          else interim += r[0].transcript
        }
        const heard = (finalText + interim).trim()
        setText(base ? (heard ? base + ' ' + heard : base) : heard)
      }
      rec.onend = () => {
        recRef.current = null
        setListening(false)
      }
      rec.onerror = (ev) => {
        recRef.current = null
        setListening(false)
        if (ev && ev.error === 'not-allowed') {
          setPlaceholder('Mic ki permission nahi mili')
          setTimeout(() => setPlaceholder('Rama se kuch poochho...'), 2000)
        }
      }
      recRef.current = rec
      rec.start()
      setListening(true)
    } catch (err) {
      setListening(false)
    }
  }

  return (
    <form className="input-bar" onSubmit={submit}>
      <div className="input-pill">
        <button type="button" className="plus-btn" onClick={pickFile} title="Photo ya file bhejo">+</button>
        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={placeholder}
        />
        {text.trim() ? (
          <button type="submit" className="send-btn" disabled={sending} title="Bhejo">➤</button>
        ) : (
          <button
            type="button"
            className={`mic-btn ${listening ? 'listening' : ''}`}
            onClick={toggleMic}
            title="Bolo"
          >
            🎤
          </button>
        )}
      </div>
      <input
        type="file"
        ref={fileRef}
        hidden
        accept="image/*,.txt,.md,.csv,.pdf"
        onChange={onFileChange}
      />
    </form>
  )
}
