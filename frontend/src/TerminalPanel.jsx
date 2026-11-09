import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { useEffect, useRef, useState } from 'react'
import '@xterm/xterm/css/xterm.css'

function websocketUrl(path) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'

  return `${protocol}//${window.location.host}${path}`
}

function TerminalPanel({ running, guestReady }) {
  const terminalElement = useRef(null)
  const [mode, setMode] = useState('serial')
  const enabled = running && (mode === 'serial' || guestReady)

  useEffect(() => {
    if (!enabled || terminalElement.current === null) {
      return
    }

    let disposed = false

    const terminal = new Terminal({
      cursorBlink: true,
      convertEol: true,
      fontFamily: 'Menlo, Monaco, monospace',
      fontSize: 14,
      theme: {
        background: '#111827',
        foreground: '#e5e7eb',
        cursor: '#f9fafb'
      }
    })

    const fitAddon = new FitAddon()

    terminal.loadAddon(fitAddon)
    terminal.open(terminalElement.current)
    fitAddon.fit()

    terminal.writeln('Подключение к терминалу...')

    const socket = new WebSocket(websocketUrl(mode === 'serial' ? '/ws/serial' : '/ws/ssh'))
    socket.binaryType = 'arraybuffer'

    const decoder = new TextDecoder()
    const encoder = new TextEncoder()

    function sendSize() {
      if (mode === 'ssh' && socket.readyState === WebSocket.OPEN) {
        socket.send('\x00resize:' + JSON.stringify({ cols: terminal.cols, rows: terminal.rows }))
      }
    }

    socket.addEventListener('open', () => {
      if (!disposed) {
        sendSize()
        terminal.writeln('\r\nТерминал подключен.\r\n')
      }
    })

    socket.addEventListener('message', (event) => {
      if (disposed) {
        return
      }

      if (typeof event.data === 'string') {
        terminal.write(event.data)
      } else {
        terminal.write(
          decoder.decode(event.data, { stream: true })
        )
      }
    })

    const modeName = mode === 'serial' ? 'Serial-консоли' : 'SSH-терминалу'
    const disconnectedText = mode === 'serial'
      ? 'Serial-консоль отключена.'
      : 'SSH-терминал отключён.'

    socket.addEventListener('error', () => {
      if (!disposed) {
        terminal.writeln(`\r\nОшибка подключения к ${modeName}.`)
      }
    })

    socket.addEventListener('close', () => {
      if (!disposed) {
        terminal.writeln(`\r\n${disconnectedText}`)
      }
    })

    const inputSubscription = terminal.onData((data) => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(mode === 'ssh' ? encoder.encode(data) : data)
      }
    })

    const resizeObserver = new ResizeObserver(() => {
      fitAddon.fit()
      sendSize()
    })

    resizeObserver.observe(terminalElement.current)

    return () => {
      disposed = true
      resizeObserver.disconnect()
      inputSubscription.dispose()
      socket.close()
      terminal.dispose()
    }
  }, [enabled, mode])

  return (
    <section className="panel terminal-panel">
      <h2>Терминал Debian</h2>

      <div className="terminal-modes">
      <button
          className={mode === 'serial' ? 'active' : ''}
          onClick={() => setMode('serial')}
      >
          Serial
      </button>

      <button
          className={mode === 'ssh' ? 'active' : ''}
          disabled={!guestReady}
          onClick={() => setMode('ssh')}
      >
          SSH
      </button>
      </div>

      {!running && (
        <p className="terminal-placeholder">
          Запустите виртуальную машину, чтобы открыть консоль.
        </p>
      )}

      {running && mode === 'ssh' && !guestReady && (
        <p className="terminal-placeholder">
          SSH станет доступен после полной загрузки Debian.
        </p>
      )}

      {enabled && (
        <div
          className="terminal-container"
          ref={terminalElement}
        />
      )}
    </section>
  )
}

export default TerminalPanel
