import { useState, useEffect, useCallback, useRef } from 'react'
import GraphViewer from './components/GraphViewer'
import ChatPanel from './components/ChatPanel'

const NODE_TYPE_CONFIG = {
  Customer: { color: '#ef4444', label: 'Customer' },
  SalesOrder: { color: '#3b82f6', label: 'Sales Order' },
  SalesOrderItem: { color: '#60a5fa', label: 'Order Item' },
  Delivery: { color: '#10b981', label: 'Delivery' },
  DeliveryItem: { color: '#34d399', label: 'Delivery Item' },
  BillingDocument: { color: '#f59e0b', label: 'Billing' },
  BillingDocumentItem: { color: '#fbbf24', label: 'Billing Item' },
  JournalEntry: { color: '#8b5cf6', label: 'Journal Entry' },
  Payment: { color: '#ec4899', label: 'Payment' },
  Product: { color: '#f97316', label: 'Product' },
  Plant: { color: '#6b7280', label: 'Plant' },
}

function App() {
  const [graphData, setGraphData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [highlightNodes, setHighlightNodes] = useState(new Set())
  const [highlightEdges, setHighlightEdges] = useState([])
  const [stats, setStats] = useState(null)

  useEffect(() => {
    fetchGraph()
    fetchStats()
  }, [])

  const fetchGraph = async () => {
    try {
      const res = await fetch('/api/graph/overview')
      const data = await res.json()
      setGraphData(data)
    } catch (err) {
      console.error('Failed to load graph:', err)
    } finally {
      setLoading(false)
    }
  }

  const fetchStats = async () => {
    try {
      const res = await fetch('/api/graph/stats')
      const data = await res.json()
      setStats(data)
    } catch (err) {
      console.error('Failed to load stats:', err)
    }
  }

  const handleHighlightNodes = useCallback((nodeIds) => {
    setHighlightNodes(new Set(nodeIds))
  }, [])

  const handleHighlightEdges = useCallback((edges) => {
    setHighlightEdges(edges || [])
  }, [])

  return (
    <div className="app">
      <header className="app-header">
        <div className="logo">
          <div className="logo-icon">G</div>
          <div className="breadcrumb">
            <span>Mapping</span>
            <span className="sep">/</span>
            <span>Order to Cash</span>
          </div>
        </div>
        {stats && (
          <div className="header-stats">
            <div className="stat">
              <span>Nodes:</span>
              <span className="stat-value">{stats.total_nodes?.toLocaleString()}</span>
            </div>
            <div className="stat">
              <span>Edges:</span>
              <span className="stat-value">{stats.total_edges?.toLocaleString()}</span>
            </div>
          </div>
        )}
      </header>
      <main className="app-content">
        <GraphViewer
          graphData={graphData}
          loading={loading}
          highlightNodes={highlightNodes}
          highlightEdges={highlightEdges}
          nodeTypeConfig={NODE_TYPE_CONFIG}
        />
        <ChatPanel
          onHighlightNodes={handleHighlightNodes}
          onHighlightEdges={handleHighlightEdges}
        />
      </main>
    </div>
  )
}

export default App
