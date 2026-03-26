import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'

const WELCOME_MESSAGE = {
  role: 'assistant',
  content: 'Hi! I can help you analyze the **Order to Cash** process.\n\nTry asking questions like:\n- *Which products have the most billing documents?*\n- *Trace the flow of sales order 740506*\n- *Find orders with incomplete flows*',
}

export default function ChatPanel({ onHighlightNodes, onHighlightEdges }) {
  const [messages, setMessages] = useState([WELCOME_MESSAGE])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const messagesEndRef = useRef()
  const inputRef = useRef()

  // Auto scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async () => {
    const query = input.trim()
    if (!query || isLoading) return

    // Add user message
    const userMsg = { role: 'user', content: query }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setIsLoading(true)

    try {
      // Build conversation history for context
      const history = messages
        .filter(m => m !== WELCOME_MESSAGE)
        .map(m => ({ role: m.role, content: m.content }))

      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query,
          conversation_history: history,
        }),
      })

      const data = await res.json()

      // Build assistant message with SQL and results
      const assistantMsg = {
        role: 'assistant',
        content: data.answer || 'I could not process that query.',
        sql: data.sql,
        rawResults: data.raw_results,
        referencedNodes: data.referenced_nodes,
      }

      setMessages(prev => [...prev, assistantMsg])

      // Highlight referenced nodes and edges on graph
      if (data.referenced_nodes?.length > 0 && onHighlightNodes) {
        onHighlightNodes(data.referenced_nodes.map(n => n.id))
      }
      if (data.referenced_edges?.length > 0 && onHighlightEdges) {
        onHighlightEdges(data.referenced_edges)
      } else if (onHighlightEdges) {
        onHighlightEdges([])
      }
    } catch (err) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: '⚠️ Failed to connect to the server. Please make sure the backend is running.',
      }])
    } finally {
      setIsLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <h2>Chat with Graph</h2>
        <div className="subtitle">Order to Cash</div>
      </div>

      <div className="chat-messages">
        {messages.map((msg, idx) => (
          <ChatMessage key={idx} message={msg} />
        ))}
        {isLoading && (
          <div className="chat-message">
            <div className="msg-avatar ai">G</div>
            <div className="msg-content">
              <div className="msg-sender">GBDM AI <span className="role">Graph Agent</span></div>
              <div className="msg-text" style={{ color: '#94a3b8' }}>
                Analyzing your question...
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input-area">
        <div className="chat-status">
          <div className={`status-dot ${isLoading ? 'loading' : ''}`} />
          {isLoading ? 'Processing query...' : 'GBDM AI is awaiting instructions'}
        </div>
        <div className="chat-input-row">
          <input
            ref={inputRef}
            className="chat-input"
            type="text"
            placeholder="Analyze anything"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
          />
          <button
            className="send-btn"
            onClick={handleSend}
            disabled={isLoading || !input.trim()}
          >
            Send
          </button>
        </div>
      </div>
    </div>
  )
}

function ChatMessage({ message }) {
  const [showSql, setShowSql] = useState(false)
  const [showResults, setShowResults] = useState(false)
  const isUser = message.role === 'user'

  return (
    <div className={`chat-message ${isUser ? 'user' : ''}`}>
      <div className={`msg-avatar ${isUser ? 'user' : 'ai'}`}>
        {isUser ? 'U' : 'G'}
      </div>
      <div className="msg-content">
        {!isUser && (
          <div className="msg-sender">
            GBDM AI <span className="role">Graph Agent</span>
          </div>
        )}
        <div className="msg-text">
          {isUser ? (
            message.content
          ) : (
            <ReactMarkdown>{message.content}</ReactMarkdown>
          )}
        </div>

        {/* SQL toggle */}
        {message.sql && (
          <>
            <button className="sql-toggle" onClick={() => setShowSql(!showSql)}>
              {showSql ? '▾' : '▸'} SQL Query
            </button>
            {showSql && (
              <div className="sql-block">{message.sql}</div>
            )}
          </>
        )}

        {/* Results table */}
        {message.rawResults?.length > 0 && (
          <>
            <button className="sql-toggle" onClick={() => setShowResults(!showResults)}>
              {showResults ? '▾' : '▸'} Raw Data ({message.rawResults.length} rows)
            </button>
            {showResults && (
              <div className="results-table-wrap">
                <table className="results-table">
                  <thead>
                    <tr>
                      {Object.keys(message.rawResults[0]).map(key => (
                        <th key={key}>{key}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {message.rawResults.slice(0, 20).map((row, i) => (
                      <tr key={i}>
                        {Object.values(row).map((val, j) => (
                          <td key={j}>{val === null ? '—' : String(val)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
