
import os
import select
import socket
import sys
import termios
import tty

from config import SERIAL_SOCKET


def main():
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(str(SERIAL_SOCKET))

        print("Подключение к serial port установлено", flush=True)
        print("Для выхода нажми Ctrl + ]", flush=True)

        stdin = sys.stdin.fileno()
        stdout = sys.stdout.fileno()
        old_settings = termios.tcgetattr(stdin)

        try:
            tty.setraw(stdin)
            connection.sendall(b"\r")

            while True:
                readable, _, _ = select.select([stdin, connection], [], [])

                if connection in readable:
                    data = connection.recv(4096)

                    if not data:
                        break

                    os.write(stdout, data)

                if stdin in readable:
                    data = os.read(stdin, 1024)

                    if not data or b"\x1d" in data:
                        break

                    connection.sendall(data)
        finally:
            termios.tcsetattr(stdin, termios.TCSADRAIN, old_settings)


if __name__ == "__main__":
    main()
