import { useEffect, useState } from 'react'
import MessageList from './components/MessageList.jsx'
import ChatInput from './components/ChatInput.jsx'
import Sidebar from './components/Sidebar.jsx'

// Vercel pe VITE_API_BASE_URL set karo (Render backend URL), local me localhost:8000
const API = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export default function App() {
  const [messages, setMessages] = useState([])
  const [conversationId, setConversationId] = useState(null)
  const [conversations, setConversations] = useState([])
  const [memories, setMemories] = useState([])
  const [typing, setTyping] = useState(false)
  const [mode, setMode] = useState('fast') // fast | deep

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

  async function sendMessage(text) {
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

  function newChat() {
    setMessages([])
    setConversationId(null)
  }

  function selectChat(id) {
    // Simple version: purani chat select karne pe uska context set hota hai
    setConversationId(id)
    setMessages([])
  }

  return (
    <div className="app">
      <Sidebar
        conversations={conversations}
        memories={memories}
        onNewChat={newChat}
        onSelectChat={selectChat}
        activeId={conversationId}
      />
      <main className="chat">
        <header className="chat-header">
          <span className="logo">🙏</span>
          <span className="title-block">
            <span className="logo-name">Rama</span>
            <span className="online">● online</span>
          </span>
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
        </header>
        <MessageList messages={messages} typing={typing} />
        <ChatInput onSend={sendMessage} sending={typing} />
      </main>
    </div>
  )
}
