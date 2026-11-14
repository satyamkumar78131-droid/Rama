export default function Sidebar({ conversations, memories, onNewChat, onSelectChat, activeId }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <span className="logo">🙏 Rama</span>
        <button className="new-chat-btn" onClick={onNewChat}>+ New chat</button>
      </div>
      <div className="sidebar-section">
        <h3>Chats</h3>
        {conversations.length === 0 && <p className="muted">Abhi koi chat nahi</p>}
        {conversations.map((c) => (
          <button
            key={c.id}
            className={`conv-item ${c.id === activeId ? 'active' : ''}`}
            onClick={() => onSelectChat(c.id)}
          >
            {c.title}
          </button>
        ))}
      </div>
      <div className="sidebar-section">
        <h3>Yaadein 💭</h3>
        {memories.length === 0 && <p className="muted">Koi yaad nahi — "yaad rakho ..." likho</p>}
        {memories.map((m) => (
          <div key={m.id} className="memory-item">
            <b>{m.key}:</b> {m.value}
          </div>
        ))}
      </div>
    </aside>
  )
}
