from contextlib import asynccontextmanager, contextmanager
import socket
import subprocess
import threading
import time
import asyncio
import logging
import json
import paramiko

from config import (
    CONTAINERIZED,
    QEMU_LOG,
    SSH_HOST,
    SSH_PORT,
    VM_START_TIMEOUT,
    VM_STOP_TIMEOUT,
)
from fastapi import FastAPI, HTTPException, WebSocket
from ssh_client import connect_ssh
from start_vm import build_command, SERIAL_SOCKET

from qmp_client import QMP_SOCKET, execute_command


@asynccontextmanager
async def lifespan(_app):
    yield

    if CONTAINERIZED:
        await asyncio.to_thread(shutdown_container_vm)


app = FastAPI(lifespan=lifespan)
VM_OPERATION_LOCK = threading.Lock()
VM_PROCESS = None
GUEST_READY_COMMAND = "systemctl is-active --quiet systemd-logind"
GUEST_READY_LOG_CHANNEL = "paramiko.transport.guest-ready"
GUEST_READY_LOGGER = logging.getLogger(GUEST_READY_LOG_CHANNEL)
GUEST_READY_LOGGER.addHandler(logging.NullHandler())
GUEST_READY_LOGGER.propagate = False


def stopped_status():
    return {
        "running": False,
        "status": "stopped",
        "guest_ready": False,
    }


@app.get("/healthz")
def healthcheck():
    return {"status": "ok"}


def ssh_available():
    try:
        with socket.create_connection((SSH_HOST, SSH_PORT), timeout=0.5) as connection:
            connection.settimeout(0.5)
            return connection.recv(64).startswith(b"SSH-")

    except OSError:
        return False


def guest_ready():
    if not ssh_available():
        return False

    try:
        client = connect_ssh(
            timeout=1,
            banner_timeout=1,
            auth_timeout=1,
            log_channel=GUEST_READY_LOG_CHANNEL,
        )

        _stdin, stdout, _stderr = client.exec_command(
            GUEST_READY_COMMAND,
            timeout=2,
        )

        return stdout.channel.recv_exit_status() == 0

    except (EOFError, OSError, paramiko.SSHException):
        return False

    finally:
        if "client" in locals():
            client.close()


@contextmanager
def vm_operation():
    if not VM_OPERATION_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Операция с VM уже выполняется")
    try:
        yield
    finally:
        VM_OPERATION_LOCK.release()


def wait_for_vm_stop(timeout=VM_STOP_TIMEOUT):
    if VM_PROCESS is None:
        return False
    try:
        VM_PROCESS.wait(timeout=timeout)
        return True
    except subprocess.TimeoutExpired:
        return False


def reap_process(process):
    process.wait()


@app.get("/api/vm/status")
def get_vm_status():
    process = VM_PROCESS
    if process is not None and process.poll() is not None:
        return stopped_status()
    if process is None and not QMP_SOCKET.exists():
        return stopped_status()
    try:
        qemu_status = execute_command("query-status", timeout=3)["return"]
        if not isinstance(qemu_status, dict):
            raise ValueError("Некорректное состояние QMP")
        # execute_command closes QMP before the potentially slow SSH check.
        is_guest_ready = bool(qemu_status.get("running")) and guest_ready()
        return {
            **qemu_status,
            "qemu_status": qemu_status["status"],
            "guest_ready": is_guest_ready,
            "pid": process.pid if process is not None else None,
        }
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


def cleanup_stale_sockets():
    if VM_PROCESS is None or VM_PROCESS.poll() is None:
        return
    for path in (QMP_SOCKET, SERIAL_SOCKET):
        path.unlink(missing_ok=True)


def powerdown_vm():
    if VM_PROCESS is None:
        raise HTTPException(
            status_code=409,
            detail="Нет управляемого процесса QEMU. Запускайте VM через этот backend.",
        )
    if VM_PROCESS.poll() is not None:
        cleanup_stale_sockets()
        raise HTTPException(status_code=409, detail="Виртуальная машина не запущена")
    try:
        execute_command("system_powerdown")
    except (OSError, ValueError, RuntimeError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if not wait_for_vm_stop():
        raise HTTPException(
            status_code=504,
            detail=f"Debian не завершила работу за {VM_STOP_TIMEOUT} секунд. "
                   "Принудительная остановка не выполнялась.",
        )
    cleanup_stale_sockets()


@app.post("/api/vm/stop")
def stop_vm():
    with vm_operation():
        powerdown_vm()
        return {"message": "Виртуальная машина выключена"}


@app.post("/api/vm/reboot")
def reboot_vm():
    with vm_operation():
        powerdown_vm()
        launch_vm()
        return {"message": "Debian штатно выключена и запускается заново"}


def shutdown_container_vm():
    with VM_OPERATION_LOCK:
        if VM_PROCESS is not None and VM_PROCESS.poll() is None:
            try:
                powerdown_vm()
            except HTTPException as error:
                logging.getLogger(__name__).warning("Остановка VM: %s", error.detail)
        cleanup_stale_sockets()


def launch_vm():
    global VM_PROCESS
    if VM_PROCESS is not None and VM_PROCESS.poll() is None:
        raise HTTPException(status_code=409, detail="Процесс QEMU уже запущен")
    cleanup_stale_sockets()
    if QMP_SOCKET.exists() or SERIAL_SOCKET.exists():
        raise HTTPException(
            status_code=409,
            detail="Обнаружены сокеты неизвестного процесса QEMU. "
                   "Сначала проверьте его состояние; сокеты не удалены.",
        )
    try:
        command = build_command()
        with open(QEMU_LOG, "ab") as log:
            VM_PROCESS = subprocess.Popen(
                command, stdin=subprocess.DEVNULL, stdout=log,
                stderr=subprocess.STDOUT, start_new_session=not CONTAINERIZED,
            )
        threading.Thread(
            target=reap_process, args=(VM_PROCESS,), daemon=True,
            name=f"qemu-reaper-{VM_PROCESS.pid}",
        ).start()
    except OSError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    deadline = time.monotonic() + VM_START_TIMEOUT
    while time.monotonic() < deadline:
        if VM_PROCESS.poll() is not None:
            cleanup_stale_sockets()
            raise HTTPException(
                status_code=500,
                detail=f"QEMU завершился с кодом {VM_PROCESS.returncode}. Проверь {QEMU_LOG}",
            )
        try:
            execute_command("query-status", timeout=1)
            return {"message": "QEMU запущен, Debian загружается", "pid": VM_PROCESS.pid}
        except (OSError, ValueError, RuntimeError):
            time.sleep(0.2)
    raise HTTPException(
        status_code=503,
        detail=f"QEMU пока не ответил по QMP. Процесс сохранён; повторный запуск "
               f"заблокирован до его завершения. Проверь {QEMU_LOG}",
    )


@app.post("/api/vm/start")
def start_vm():
    with vm_operation():
        return launch_vm()


@app.websocket("/ws/serial")
async def serial_terminal(websocket: WebSocket):
    await websocket.accept()

    try:
        reader, writer = await asyncio.open_unix_connection(
            str(SERIAL_SOCKET)
        )
    except OSError:
        await websocket.close(code=1011)
        return

    async def read_serial():
        while True:
            data = await reader.read(4096)

            if not data:
                break

            await websocket.send_bytes(data)

    async def write_serial():
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                break

            data = message.get("bytes")

            if data is None:
                data = (message.get("text") or "").encode("utf-8")

            if data:
                writer.write(data)
                await writer.drain()

    tasks = [
        asyncio.create_task(read_serial()),
        asyncio.create_task(write_serial()),
    ]

    try:
        done, pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED
        )

        for task in pending:
            task.cancel()

        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        writer.close()
        await writer.wait_closed()


def create_ssh_session():
    client = connect_ssh(timeout=10)

    try:
        channel = client.invoke_shell(
            term="xterm",
            width=100,
            height=30
        )

        return client, channel

    except Exception:
        client.close()
        raise


@app.websocket("/ws/ssh")
async def ssh_terminal(websocket: WebSocket):
    await websocket.accept()

    try:
        client, channel = await asyncio.to_thread(
            create_ssh_session
        )

    except (OSError, paramiko.SSHException) as error:
        print(f"Ошибка SSH: {error}", flush=True)
        await websocket.close(code=1011)
        return

    async def read_ssh():
        while not channel.closed:
            if channel.recv_ready():
                data = channel.recv(4096)

                if not data:
                    break

                await websocket.send_bytes(data)

            elif channel.exit_status_ready():
                break

            else:
                await asyncio.sleep(0.05)

    async def write_ssh():
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            data = message.get("bytes")
            text = message.get("text") or ""
            # Binary frames carry input; prefixed text frames carry resize only.
            if data is None and text.startswith("\x00resize:"):
                try:
                    size = json.loads(text[len("\x00resize:"):])
                    if not isinstance(size, dict):
                        continue
                    cols, rows = size.get("cols"), size.get("rows")
                    if type(cols) is int and type(rows) is int and 1 <= cols <= 1000 and 1 <= rows <= 1000:
                        await asyncio.to_thread(channel.resize_pty, width=cols, height=rows)
                except (ValueError, TypeError):
                    pass
                continue
            if data is None:
                data = text.encode("utf-8")
            if data:
                await asyncio.to_thread(channel.sendall, data)

    tasks = [
        asyncio.create_task(read_ssh()),
        asyncio.create_task(write_ssh())
    ]

    try:
        done, pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED
        )

        for task in pending:
            task.cancel()

        await asyncio.gather(*tasks, return_exceptions=True)

    finally:
        channel.close()
        client.close()
