/**
 * WebSocket 客户端单例。
 *
 * 用于实时匹配会话中的双向消息推送：
 * - 匹配成功通知（match_found）
 * - 临时聊天消息（match_chat）
 * - 关注事件（match_follow_event）
 * - 求关注请求（match_request_follow）
 * - 会话结束（match_end / match_timeout）
 *
 * 鉴权：通过 query 参数 token 传递 access_token。
 * 后端 /ws 端点解码 token 获取 user_id，注册到 ConnectionManager。
 */
import { ref, type Ref } from 'vue'

export type WsMessageHandler = (msg: WsMessage) => void

export interface WsMessage {
  type: string
  [key: string]: unknown
}

class WsClient {
  /** 当前 WebSocket 连接（单例） */
  private ws: WebSocket | null = null
  /** 重连定时器 */
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  /** 心跳定时器 */
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null
  /** 消息处理器列表 */
  private handlers: Set<WsMessageHandler> = new Set()
  /** 连接状态（响应式） */
  public connected: Ref<boolean> = ref(false)
  /** 是否主动关闭（避免主动关闭后还触发重连） */
  private manualClose = false
  /** 重连次数（最多 5 次，避免无限重连） */
  private reconnectAttempts = 0

  /** 连接 WebSocket（利用浏览器自动携带同源 Cookie 进行鉴权） */
  connect(): void {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      // 已连接或正在连接，直接返回
      return
    }
    this.manualClose = false
    this.reconnectAttempts = 0
    this._doConnect()
  }

  private _doConnect(): void {
    try {
      const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
      const host = window.location.host
      // 注意：URL 必须是 /ws（不能是 /api/ws）。
      // vite.config.ts 中只有 /ws 代理启用了 ws:true，/api 代理未启用 ws:true，
      // 使用 /api/ws 会导致 WebSocket 握手失败、连接永远建立不起来。
      // 浏览器 WebSocket 会自动携带同源 Cookie（含 httponly 的 access_token），
      // 后端从 Cookie 中解析 access_token 完成鉴权。
      const url = `${proto}://${host}/ws`
      this.ws = new WebSocket(url)
    } catch (err) {
      console.warn('[WS] create failed:', err)
      this._scheduleReconnect()
      return
    }

    this.ws.onopen = () => {
      this.connected.value = true
      this.reconnectAttempts = 0
      this._startHeartbeat()
    }

    this.ws.onmessage = (event: MessageEvent) => {
      try {
        const msg = JSON.parse(event.data) as WsMessage
        this.handlers.forEach((h) => {
          try {
            h(msg)
          } catch (err) {
            console.warn('[WS] handler error:', err)
          }
        })
      } catch (err) {
        console.warn('[WS] parse message failed:', err)
      }
    }

    this.ws.onclose = () => {
      this.connected.value = false
      this._stopHeartbeat()
      if (!this.manualClose) {
        this._scheduleReconnect()
      }
    }

    this.ws.onerror = () => {
      // 错误处理已在 onclose 中触发重连
      try {
        this.ws?.close()
      } catch {
        /* ignore */
      }
    }
  }

  private _scheduleReconnect(): void {
    if (this.reconnectTimer) return
    if (this.reconnectAttempts >= 5) {
      console.warn('[WS] max reconnect attempts reached, give up')
      return
    }
    this.reconnectAttempts += 1
    const delay = Math.min(1000 * this.reconnectAttempts, 5000)
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this._doConnect()
    }, delay)
  }

  private _startHeartbeat(): void {
    this._stopHeartbeat()
    // 每 25 秒发一次心跳，避免代理超时断开
    this.heartbeatTimer = setInterval(() => {
      this.send({ type: 'ping' })
    }, 25000)
  }

  private _stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
  }

  /** 发送消息 */
  send(msg: WsMessage): boolean {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return false
    }
    try {
      this.ws.send(JSON.stringify(msg))
      return true
    } catch (err) {
      console.warn('[WS] send failed:', err)
      return false
    }
  }

  /** 注册消息处理器，返回取消注册函数 */
  on(handler: WsMessageHandler): () => void {
    this.handlers.add(handler)
    return () => {
      this.handlers.delete(handler)
    }
  }

  /** 主动断开 */
  disconnect(): void {
    this.manualClose = true
    this._stopHeartbeat()
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    if (this.ws) {
      try {
        this.ws.close()
      } catch {
        /* ignore */
      }
      this.ws = null
    }
    this.connected.value = false
  }
}

export const wsClient = new WsClient()

/** 连接 WebSocket（如已连接则跳过）。鉴权依赖浏览器自动携带的同源 Cookie。 */
export function connectWs(): void {
  wsClient.connect()
}
