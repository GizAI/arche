import { ref, onMounted, onUnmounted } from 'vue'
import { useAgentStore } from '@/stores/agent'

export function useLogsWebSocket() {
  const store = useAgentStore()
  const ws = ref<WebSocket | null>(null)
  const reconnectAttempts = ref(0)
  const maxReconnectAttempts = 10

  function connect() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    ws.value = new WebSocket(`${protocol}//${host}/ws/logs`)

    ws.value.onopen = () => {
      store.setWsConnected(true)
      reconnectAttempts.value = 0
    }

    ws.value.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (data.type === 'init') {
        store.setLogs(data.content)
      } else if (data.type === 'append') {
        store.appendLog(data.content)
      }
      // Ignore ping messages
    }

    ws.value.onclose = () => {
      store.setWsConnected(false)
      // Attempt reconnect
      if (reconnectAttempts.value < maxReconnectAttempts) {
        reconnectAttempts.value++
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.value), 30000)
        setTimeout(connect, delay)
      }
    }

    ws.value.onerror = () => {
      ws.value?.close()
    }
  }

  function disconnect() {
    reconnectAttempts.value = maxReconnectAttempts // Prevent reconnection
    ws.value?.close()
  }

  onMounted(connect)
  onUnmounted(disconnect)

  return { ws, reconnectAttempts }
}

export function useEventsWebSocket(onStateChange?: (state: any) => void) {
  const ws = ref<WebSocket | null>(null)
  const reconnectAttempts = ref(0)
  const maxReconnectAttempts = 10

  function connect() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    ws.value = new WebSocket(`${protocol}//${host}/ws/events`)

    ws.value.onopen = () => {
      reconnectAttempts.value = 0
    }

    ws.value.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (data.type === 'state' && onStateChange) {
        onStateChange(data)
      }
    }

    ws.value.onclose = () => {
      if (reconnectAttempts.value < maxReconnectAttempts) {
        reconnectAttempts.value++
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.value), 30000)
        setTimeout(connect, delay)
      }
    }

    ws.value.onerror = () => {
      ws.value?.close()
    }
  }

  function disconnect() {
    reconnectAttempts.value = maxReconnectAttempts
    ws.value?.close()
  }

  onMounted(connect)
  onUnmounted(disconnect)

  return { ws, reconnectAttempts }
}
