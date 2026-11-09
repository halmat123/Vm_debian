import asyncio
import codecs
import os
import uuid

import websockets


async def main():
    base_url = os.getenv(
        "WS_BASE_URL", f"ws://127.0.0.1:{os.getenv('WEB_PORT', '8080')}"
    ).rstrip("/")
    marker = "SERIAL_TEST_" + uuid.uuid4().hex
    expected = marker + ":" + os.getenv("SSH_USER", "debian")
    command = "printf '" + marker + ":%s\\n' \"$(whoami)\"\r"
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    async with websockets.connect(base_url + "/ws/serial") as connection:
        await connection.send(command)
        output = ""
        async with asyncio.timeout(30):
            while expected not in output:
                data = await connection.recv()
                text = decoder.decode(data) if isinstance(data, bytes) else data
                print(text, end="", flush=True)
                output += text
        print("\nПроверка serial успешна: whoami вернул ожидаемого пользователя")


if __name__ == "__main__":
    asyncio.run(main())
