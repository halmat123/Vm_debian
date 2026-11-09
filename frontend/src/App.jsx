
import { useEffect, useRef, useState } from 'react'
import './App.css'
import TerminalPanel from './TerminalPanel'

async function readResponse(response) {
  const text = await response.text()
  let result
  try {
    result = JSON.parse(text)
  } catch {
    throw new Error(`Сервер вернул некорректный ответ (HTTP ${response.status})`)
  }
  if (!response.ok) {
    throw new Error(typeof result?.detail === 'string'
      ? result.detail
      : `Ошибка сервера (HTTP ${response.status})`)
  }
  if (!result || typeof result !== 'object' || Array.isArray(result)) {
    throw new Error('Некорректный формат ответа сервера')
  }
  return result
}

function App() {
  const [vm, setVm] = useState(null)
  const [statusError, setStatusError] = useState('')
  const [commandError, setCommandError] = useState('')
  const [sending, setSending] = useState(false)
  const [pending, setPending] = useState(null)
  const statusRequest = useRef(0)

  async function refreshStatus() {
    const request = ++statusRequest.current
    try {
      const response = await fetch('/api/vm/status')
      const data = await readResponse(response)
      if (request !== statusRequest.current) return
      setVm(data)
      setStatusError('')
    } catch (err) {
      if (request !== statusRequest.current) return
      setVm(null)
      setStatusError(err.message)
    }
  }

  useEffect(() => {
    let cancelled = false
    let timer
    async function poll() {
      await refreshStatus()
      if (!cancelled) timer = setTimeout(poll, 3000)
    }
    timer = setTimeout(poll, 0)
    return () => {
      cancelled = true
      clearTimeout(timer)
      statusRequest.current += 1
    }
  }, [])

  async function sendCommand(action) {
    if (sending || pending || vm === null) {
      return
    }

    setSending(true)
    setCommandError('')

    setPending({ action })

    try {
      const response = await fetch(`/api/vm/${action}`, {
        method: 'POST'
      })

      await readResponse(response)

      await refreshStatus()
    } catch (err) {
      setPending(null)
      setCommandError(err.message)
    } finally {
      setPending(null)
      setSending(false)
    }
  }

  const busy = sending || pending !== null

  let statusText = 'Неизвестно'

  if (pending?.action === 'start') {
    statusText = 'Запускается...'
  } else if (pending?.action === 'stop') {
    statusText = 'Выключается...'
  } else if (pending?.action === 'reboot') {
    statusText = 'Перезагружается...'
  } else if (sending) {
    statusText = 'Выполняется команда...'
  } else if (vm !== null) {
    if (!vm.running) {
      statusText = 'Выключена'
    } else if (!vm.guest_ready) {
      statusText = 'Работает; SSH пока недоступен'
    } else {
      statusText = 'Работает'
    }
  }

  return (
    <main className="container">
      <h1>YADRO VM Manager</h1>
      <p className="description">Управление виртуальной машиной Debian 13</p>

      <section className="panel">
        <h2>Виртуальная машина</h2>

        <p>
          Состояние: <strong>{statusText}</strong>
        </p>

        <div className="buttons">
          <button
            disabled={busy || vm === null || vm.running}
            onClick={() => sendCommand('start')}
          >
            Включить
          </button>

          <button
            disabled={busy || !vm?.running}
            onClick={() => sendCommand('reboot')}
          >
            Перезагрузить
          </button>

          <button
            disabled={busy || !vm?.running}
            onClick={() => sendCommand('stop')}
          >
            Выключить
          </button>
        </div>

        {statusError && <p className="error">{statusError}</p>}
        {commandError && <p className="error">{commandError}</p>}
        </section>

        <TerminalPanel
          key={vm?.pid ?? 'external'}
          running={vm?.running === true}
          guestReady={vm?.guest_ready === true}
        />
      </main>
  )
}

export default App
