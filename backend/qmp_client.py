
import json
import socket
import sys
import threading
import os
import urllib.request

from config import QMP_SOCKET, VM_START_TIMEOUT, VM_STOP_TIMEOUT

QMP_LOCK = threading.Lock()

COMMANDS = {
    "status": "query-status",
    "stop": "system_powerdown",
}


def read_reply(reader):
    while True:
        line = reader.readline()

        if not line:
            raise ConnectionError("QEMU закрыл соединение")

        response = json.loads(line)

        if not isinstance(response, dict):
            raise ValueError("Некорректный ответ QMP")

        if "event" in response:
            print("Событие QEMU:", response["event"])
            continue

        return response


def send_command(connection, reader, command):
    request = {"execute": command}
    data = json.dumps(request) + "\n"

    connection.sendall(data.encode("utf-8"))

    response = read_reply(reader)

    if "error" in response:
        raise RuntimeError(response["error"])

    if "return" not in response:
        raise ValueError("В ответе QMP нет результата команды")

    print(f"{command}: {response}")
    return response


def execute_command(command, timeout=5):
    with QMP_LOCK:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(timeout)
            connection.connect(str(QMP_SOCKET))
            with connection.makefile("r", encoding="utf-8") as reader:
                greeting = read_reply(reader)
                if "QMP" not in greeting:
                    raise ValueError("Некорректное приветствие QMP")
                send_command(connection, reader, "qmp_capabilities")
                return send_command(connection, reader, command)


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    if action == "reboot":
        base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
        request = urllib.request.Request(base_url + "/api/vm/reboot", method="POST")
        with urllib.request.urlopen(
            request, timeout=VM_STOP_TIMEOUT + VM_START_TIMEOUT + 15,
        ) as response:
            print(response.read().decode("utf-8"))
        return
    if action not in COMMANDS:
        raise SystemExit(
            "Доступные команды: status, reboot, stop. "
            "reboot обращается к backend (API_BASE_URL)."
        )
    execute_command(COMMANDS[action])


if __name__ == "__main__":
    main()
