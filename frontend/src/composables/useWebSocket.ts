import { ref, onMounted, onUnmounted } from 'vue'
import { useAgentStore } from '@/stores/agent'

function createWebSocket(path: string): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return new WebSocket(`${protocol}//${window.location.host}${path}`)
}

export function useLogsWebSocket() {
  const store = useAgentStore()
  const ws = ref<WebSocket | null>(null)
  const reconnectAttempts = ref(0)
  const maxReconnectAttempts = 10

  function connect() {
    ws.value = createWebSocket('/ws/logs')

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
    }

    ws.value.onclose = () => {
      store.setWsConnected(false)
      if (reconnectAttempts.value < maxReconnectAttempts) {
        reconnectAttempts.value++
        setTimeout(connect, Math.min(1000 * 2 ** reconnectAttempts.value, 30000))
      }
    }

    ws.value.onerror = () => ws.value?.close()
  }

  function disconnect() {
    reconnectAttempts.value = maxReconnectAttempts
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
    ws.value = createWebSocket('/ws/events')

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
        setTimeout(connect, Math.min(1000 * 2 ** reconnectAttempts.value, 30000))
      }
    }

    ws.value.onerror = () => ws.value?.close()
  }

  function disconnect() {
    reconnectAttempts.value = maxReconnectAttempts
    ws.value?.close()
  }

  onMounted(connect)
  onUnmounted(disconnect)

  return { ws, reconnectAttempts }
}
