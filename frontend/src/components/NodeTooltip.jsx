import { useEffect, useRef } from 'react'

const MAX_VISIBLE_FIELDS = 12

export default function NodeTooltip({ node, metadata, position, onClose }) {
  const tooltipRef = useRef()

  // Position the tooltip within viewport bounds
  useEffect(() => {
    if (!tooltipRef.current) return
    const rect = tooltipRef.current.getBoundingClientRect()
    const el = tooltipRef.current

    let left = position.x + 15
    let top = position.y - 20

    // Keep within viewport
    if (left + rect.width > window.innerWidth - 20) {
      left = position.x - rect.width - 15
    }
    if (top + rect.height > window.innerHeight - 20) {
      top = window.innerHeight - rect.height - 20
    }
    if (top < 60) top = 60

    el.style.left = `${left}px`
    el.style.top = `${top}px`
  }, [position, metadata])

  // Close on click outside
  useEffect(() => {
    const handler = (e) => {
      if (tooltipRef.current && !tooltipRef.current.contains(e.target)) {
        onClose()
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [onClose])

  const [nodeType] = node.id.split(':')

  // Get type color
  const typeColors = {
    Customer: '#ef4444',
    SalesOrder: '#3b82f6',
    SalesOrderItem: '#60a5fa',
    Delivery: '#10b981',
    DeliveryItem: '#34d399',
    BillingDocument: '#f59e0b',
    BillingDocumentItem: '#fbbf24',
    JournalEntry: '#8b5cf6',
    Payment: '#ec4899',
    Product: '#f97316',
    Plant: '#6b7280',
  }

  const typeName = nodeType.replace(/([A-Z])/g, ' $1').trim()
  const color = typeColors[nodeType] || '#6b7280'

  // Format field values for display
  const formatValue = (val) => {
    if (val === null || val === undefined) return '—'
    if (typeof val === 'boolean') return val ? 'Yes' : 'No'
    if (typeof val === 'number') {
      if (Number.isInteger(val) && (val === 0 || val === 1)) return val ? 'Yes' : 'No'
    }
    return String(val)
  }

  const data = metadata?.data
  const fields = data ? (Array.isArray(data) ? data[0] : data) : null
  const entries = fields ? Object.entries(fields) : []
  const visibleEntries = entries.slice(0, MAX_VISIBLE_FIELDS)
  const hiddenCount = Math.max(0, entries.length - MAX_VISIBLE_FIELDS)

  return (
    <div className="node-tooltip" ref={tooltipRef} style={{ left: position.x + 15, top: position.y - 20 }}>
      <button className="tooltip-close" onClick={onClose}>×</button>
      <h3>
        <span className="type-badge" style={{ background: color + '20', color: color }}>
          {typeName}
        </span>
      </h3>

      {!metadata && (
        <div style={{ padding: '20px 0', textAlign: 'center', color: '#94a3b8', fontSize: 13 }}>
          Loading...
        </div>
      )}

      {fields && (
        <>
          <div className="fields">
            <div className="field-row">
              <span className="field-name">Entity:</span>
              <span className="field-value">{typeName}</span>
            </div>
            {visibleEntries.map(([key, value]) => (
              <div key={key} className="field-row">
                <span className="field-name">{key}:</span>
                <span className="field-value">{formatValue(value)}</span>
              </div>
            ))}
          </div>

          {hiddenCount > 0 && (
            <div className="hidden-fields">
              Additional fields hidden for readability
            </div>
          )}

          {metadata.connections !== undefined && (
            <div className="connections">
              Connections: {metadata.connections}
            </div>
          )}
        </>
      )}
    </div>
  )
}
