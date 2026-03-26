import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import NodeTooltip from './NodeTooltip'

const NODE_TYPE_CONFIG = {
  Customer: { color: '#ef4444', size: 8 },
  SalesOrder: { color: '#3b82f6', size: 5 },
  SalesOrderItem: { color: '#60a5fa', size: 3 },
  Delivery: { color: '#10b981', size: 5 },
  DeliveryItem: { color: '#34d399', size: 3 },
  BillingDocument: { color: '#f59e0b', size: 5 },
  BillingDocumentItem: { color: '#fbbf24', size: 3 },
  JournalEntry: { color: '#8b5cf6', size: 5 },
  Payment: { color: '#ec4899', size: 5 },
  Product: { color: '#f97316', size: 4 },
  Plant: { color: '#6b7280', size: 4 },
}

const LEGEND = [
  { type: 'Customer', color: '#ef4444' },
  { type: 'Sales Order', color: '#3b82f6' },
  { type: 'Delivery', color: '#10b981' },
  { type: 'Billing', color: '#f59e0b' },
  { type: 'Journal Entry', color: '#8b5cf6' },
  { type: 'Payment', color: '#ec4899' },
  { type: 'Product', color: '#f97316' },
  { type: 'Plant', color: '#6b7280' },
]

// Edge type to color mapping for distinct highlight colors
const EDGE_TYPE_COLORS = {
  PLACED_ORDER: '#ef4444',
  HAS_ITEM: '#60a5fa',
  CONTAINS_PRODUCT: '#f97316',
  FULFILLED_BY: '#10b981',
  DELIVERY_HAS_ITEM: '#34d399',
  SHIPPED_FROM: '#6b7280',
  BILLED_FOR: '#f59e0b',
  BILLING_HAS_ITEM: '#fbbf24',
  POSTED_TO: '#8b5cf6',
  CLEARED_BY: '#ec4899',
  BILLED_TO: '#f59e0b',
  PRODUCED_AT: '#f97316',
}

export default function GraphViewer({ graphData, loading, highlightNodes, highlightEdges = [] }) {
  const graphRef = useRef()
  const containerRef = useRef()
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 })
  const [selectedNode, setSelectedNode] = useState(null)
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 })
  const [nodeMetadata, setNodeMetadata] = useState(null)
  const [showGranular, setShowGranular] = useState(false)
  const [hoveredNode, setHoveredNode] = useState(null)

  // Build a Set of highlighted edge keys for fast lookup
  const highlightEdgeSet = useMemo(() => {
    const set = new Set()
    for (const e of highlightEdges) {
      set.add(`${e.source}->${e.target}`)
    }
    return set
  }, [highlightEdges])

  // Map edge keys to their type (for coloring)
  const highlightEdgeTypes = useMemo(() => {
    const map = new Map()
    for (const e of highlightEdges) {
      map.set(`${e.source}->${e.target}`, e.type)
    }
    return map
  }, [highlightEdges])

  // Resize handler
  useEffect(() => {
    const updateSize = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.offsetWidth,
          height: containerRef.current.offsetHeight,
        })
      }
    }
    updateSize()
    window.addEventListener('resize', updateSize)
    return () => window.removeEventListener('resize', updateSize)
  }, [])

  // Zoom to fit on data load
  useEffect(() => {
    if (graphData && graphRef.current) {
      setTimeout(() => {
        graphRef.current.zoomToFit(400, 60)
      }, 500)
    }
  }, [graphData])

  // Auto-zoom to highlighted subgraph when edges change
  useEffect(() => {
    if (highlightEdges.length > 0 && highlightNodes.size > 0 && graphRef.current) {
      setTimeout(() => {
        const nodePositions = []
        if (graphData) {
          for (const node of graphData.nodes) {
            if (highlightNodes.has(node.id) && node.x != null && node.y != null) {
              nodePositions.push({ x: node.x, y: node.y })
            }
          }
        }
        if (nodePositions.length > 0) {
          const padding = 80
          const minX = Math.min(...nodePositions.map(p => p.x)) - padding
          const maxX = Math.max(...nodePositions.map(p => p.x)) + padding
          const minY = Math.min(...nodePositions.map(p => p.y)) - padding
          const maxY = Math.max(...nodePositions.map(p => p.y)) + padding
          const cx = (minX + maxX) / 2
          const cy = (minY + maxY) / 2
          const rangeX = maxX - minX
          const rangeY = maxY - minY
          const { width, height } = dimensions
          const zoom = Math.min(width / rangeX, height / rangeY, 4)
          graphRef.current.centerAt(cx, cy, 800)
          graphRef.current.zoom(zoom, 800)
        }
      }, 300)
    }
  }, [highlightEdges, highlightNodes, graphData, dimensions])

  // Filter granular nodes (items) when toggle is off
  const filteredData = useMemo(() => {
    if (!graphData) return { nodes: [], links: [] }
    if (showGranular) return graphData

    const granularTypes = new Set(['SalesOrderItem', 'DeliveryItem', 'BillingDocumentItem'])
    const visibleNodes = graphData.nodes.filter(n => !granularTypes.has(n.type))
    const visibleIds = new Set(visibleNodes.map(n => n.id))
    const visibleLinks = graphData.links.filter(l => {
      const sourceId = typeof l.source === 'object' ? l.source.id : l.source
      const targetId = typeof l.target === 'object' ? l.target.id : l.target
      return visibleIds.has(sourceId) && visibleIds.has(targetId)
    })
    return { nodes: visibleNodes, links: visibleLinks }
  }, [graphData, showGranular])

  const handleNodeClick = useCallback(async (node, event) => {
    setSelectedNode(node)
    setTooltipPos({ x: event.clientX, y: event.clientY })
    setNodeMetadata(null)

    const [type, id] = node.id.split(':')
    try {
      const res = await fetch(`/api/graph/node/${type}/${id}`)
      const data = await res.json()
      setNodeMetadata(data)
    } catch (err) {
      console.error('Failed to fetch node metadata:', err)
    }
  }, [])

  const handleNodeHover = useCallback((node) => {
    setHoveredNode(node)
    if (containerRef.current) {
      containerRef.current.style.cursor = node ? 'pointer' : 'default'
    }
  }, [])

  const nodeCanvasObject = useCallback((node, ctx, globalScale) => {
    const config = NODE_TYPE_CONFIG[node.type] || { color: '#999', size: 4 }
    const size = config.size
    const isHighlighted = highlightNodes.has(node.id)
    const isHovered = hoveredNode?.id === node.id
    const isSelected = selectedNode?.id === node.id

    // Glow effect for highlighted nodes
    if (isHighlighted) {
      ctx.beginPath()
      ctx.arc(node.x, node.y, size + 6, 0, 2 * Math.PI)
      ctx.fillStyle = config.color + '20'
      ctx.fill()

      ctx.beginPath()
      ctx.arc(node.x, node.y, size + 4, 0, 2 * Math.PI)
      ctx.fillStyle = config.color + '35'
      ctx.fill()

      ctx.beginPath()
      ctx.arc(node.x, node.y, size + 2, 0, 2 * Math.PI)
      ctx.fillStyle = config.color + '50'
      ctx.fill()
    }

    // Node circle
    ctx.beginPath()
    ctx.arc(node.x, node.y, size, 0, 2 * Math.PI)

    if (isSelected || isHovered) {
      ctx.fillStyle = config.color
      ctx.fill()
      ctx.strokeStyle = '#fff'
      ctx.lineWidth = 2
      ctx.stroke()
    } else if (isHighlighted) {
      ctx.fillStyle = config.color
      ctx.fill()
      ctx.strokeStyle = '#fff'
      ctx.lineWidth = 2
      ctx.stroke()
    } else {
      ctx.fillStyle = '#fff'
      ctx.fill()
      ctx.strokeStyle = config.color
      ctx.lineWidth = 1.5
      ctx.stroke()
    }

    // Label for larger nodes when zoomed in
    if (globalScale > 1.5 && size >= 4) {
      const label = node.label || ''
      const fontSize = Math.max(10 / globalScale, 3)
      ctx.font = `${fontSize}px Inter, sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'top'
      ctx.fillStyle = isHighlighted ? config.color : '#64748b'
      ctx.fillText(label, node.x, node.y + size + 2)
    }
  }, [highlightNodes, hoveredNode, selectedNode])

  const linkCanvasObject = useCallback((link, ctx) => {
    const sourceId = typeof link.source === 'object' ? link.source.id : link.source
    const targetId = typeof link.target === 'object' ? link.target.id : link.target
    const edgeKey = `${sourceId}->${targetId}`
    const isEdgeHighlighted = highlightEdgeSet.has(edgeKey)
    const isNodeHighlighted = highlightNodes.has(sourceId) || highlightNodes.has(targetId)

    const sx = link.source.x
    const sy = link.source.y
    const tx = link.target.x
    const ty = link.target.y

    if (isEdgeHighlighted) {
      // ── Highlighted edge: bold + glow + arrow ──
      const edgeType = highlightEdgeTypes.get(edgeKey) || 'PLACED_ORDER'
      const edgeColor = EDGE_TYPE_COLORS[edgeType] || '#3b82f6'

      // Outer glow (widest, most transparent)
      ctx.beginPath()
      ctx.moveTo(sx, sy)
      ctx.lineTo(tx, ty)
      ctx.strokeStyle = edgeColor + '18'
      ctx.lineWidth = 10
      ctx.stroke()

      // Mid glow
      ctx.beginPath()
      ctx.moveTo(sx, sy)
      ctx.lineTo(tx, ty)
      ctx.strokeStyle = edgeColor + '35'
      ctx.lineWidth = 6
      ctx.stroke()

      // Core bold line
      ctx.beginPath()
      ctx.moveTo(sx, sy)
      ctx.lineTo(tx, ty)
      ctx.strokeStyle = edgeColor
      ctx.lineWidth = 2.5
      ctx.lineCap = 'round'
      ctx.stroke()

      // Arrow head at target
      const angle = Math.atan2(ty - sy, tx - sx)
      const arrowLen = 8
      const arrowOffsetX = tx - Math.cos(angle) * 8
      const arrowOffsetY = ty - Math.sin(angle) * 8
      ctx.beginPath()
      ctx.moveTo(arrowOffsetX, arrowOffsetY)
      ctx.lineTo(
        arrowOffsetX - arrowLen * Math.cos(angle - Math.PI / 7),
        arrowOffsetY - arrowLen * Math.sin(angle - Math.PI / 7)
      )
      ctx.lineTo(
        arrowOffsetX - arrowLen * Math.cos(angle + Math.PI / 7),
        arrowOffsetY - arrowLen * Math.sin(angle + Math.PI / 7)
      )
      ctx.closePath()
      ctx.fillStyle = edgeColor
      ctx.fill()

      // Edge type label at midpoint
      const mx = (sx + tx) / 2
      const my = (sy + ty) / 2
      ctx.font = '3px Inter, sans-serif'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      const labelText = edgeType.replace(/_/g, ' ')
      const textWidth = ctx.measureText(labelText).width
      ctx.fillStyle = 'rgba(255,255,255,0.85)'
      ctx.fillRect(mx - textWidth / 2 - 2, my - 2.5, textWidth + 4, 5)
      ctx.fillStyle = edgeColor
      ctx.fillText(labelText, mx, my)

    } else {
      // ── Default dim edge ──
      ctx.beginPath()
      ctx.moveTo(sx, sy)
      ctx.lineTo(tx, ty)

      if (isNodeHighlighted) {
        ctx.strokeStyle = 'rgba(148, 163, 184, 0.35)'
        ctx.lineWidth = 0.8
      } else {
        ctx.strokeStyle = highlightEdges.length > 0
          ? 'rgba(148, 163, 184, 0.08)'
          : 'rgba(148, 163, 184, 0.2)'
        ctx.lineWidth = 0.5
      }
      ctx.stroke()
    }
  }, [highlightNodes, highlightEdgeSet, highlightEdgeTypes, highlightEdges])

  // ── Built-in directional particles for highlighted edges (no simulation reheat) ──
  const getParticleCount = useCallback((link) => {
    const sourceId = typeof link.source === 'object' ? link.source.id : link.source
    const targetId = typeof link.target === 'object' ? link.target.id : link.target
    return highlightEdgeSet.has(`${sourceId}->${targetId}`) ? 4 : 0
  }, [highlightEdgeSet])

  const getParticleWidth = useCallback((link) => {
    const sourceId = typeof link.source === 'object' ? link.source.id : link.source
    const targetId = typeof link.target === 'object' ? link.target.id : link.target
    return highlightEdgeSet.has(`${sourceId}->${targetId}`) ? 3 : 0
  }, [highlightEdgeSet])

  const getParticleColor = useCallback((link) => {
    const sourceId = typeof link.source === 'object' ? link.source.id : link.source
    const targetId = typeof link.target === 'object' ? link.target.id : link.target
    const edgeKey = `${sourceId}->${targetId}`
    const edgeType = highlightEdgeTypes.get(edgeKey)
    return EDGE_TYPE_COLORS[edgeType] || '#3b82f6'
  }, [highlightEdgeTypes])

  return (
    <div className="graph-panel" ref={containerRef}>
      {loading && (
        <div className="loading-overlay">
          <div className="loader">
            <div className="loader-spinner" />
            <div className="loader-text">Loading graph data...</div>
          </div>
        </div>
      )}

      <div className="graph-controls">
        <button onClick={() => graphRef.current?.zoomToFit(400, 60)}>
          ✦ Fit View
        </button>
        <button
          className={showGranular ? 'active' : ''}
          onClick={() => setShowGranular(!showGranular)}
        >
          ◎ {showGranular ? 'Hide' : 'Show'} Granular Overlay
        </button>
        {highlightEdges.length > 0 && (
          <div className="highlight-badge">
            ⚡ {highlightEdges.length} edge{highlightEdges.length > 1 ? 's' : ''} highlighted
          </div>
        )}
      </div>

      {filteredData.nodes.length > 0 && (
        <ForceGraph2D
          ref={graphRef}
          graphData={filteredData}
          width={dimensions.width}
          height={dimensions.height}
          nodeCanvasObject={nodeCanvasObject}
          linkCanvasObject={linkCanvasObject}
          onNodeClick={handleNodeClick}
          onNodeHover={handleNodeHover}
          nodeId="id"
          cooldownTicks={100}
          d3AlphaDecay={0.02}
          d3VelocityDecay={0.3}
          linkDirectionalParticles={getParticleCount}
          linkDirectionalParticleSpeed={0.005}
          linkDirectionalParticleWidth={getParticleWidth}
          linkDirectionalParticleColor={getParticleColor}
          enableNodeDrag={true}
          enableZoomInteraction={true}
          enablePanInteraction={true}
          minZoom={0.1}
          maxZoom={10}
        />
      )}

      <div className="graph-legend">
        {LEGEND.map(item => (
          <div key={item.type} className="legend-item">
            <div className="legend-dot" style={{ background: item.color }} />
            {item.type}
          </div>
        ))}
      </div>

      {selectedNode && (
        <NodeTooltip
          node={selectedNode}
          metadata={nodeMetadata}
          position={tooltipPos}
          onClose={() => { setSelectedNode(null); setNodeMetadata(null) }}
        />
      )}
    </div>
  )
}
