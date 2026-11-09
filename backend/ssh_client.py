import paramiko

from config import (
    SSH_HOST,
    SSH_KNOWN_HOSTS,
    SSH_PORT,
    SSH_PRIVATE_KEY,
    SSH_TRUST_ON_FIRST_USE,
    SSH_USER,
)

SSH_KEY = SSH_PRIVATE_KEY


def connect_ssh(
    timeout=10,
    banner_timeout=None,
    auth_timeout=None,
    log_channel=None,
):
    client = paramiko.SSHClient()
    client.load_system_host_keys()

    if SSH_TRUST_ON_FIRST_USE:
        SSH_KNOWN_HOSTS.parent.mkdir(parents=True, exist_ok=True)
        SSH_KNOWN_HOSTS.touch(mode=0o600, exist_ok=True)
        client.load_host_keys(str(SSH_KNOWN_HOSTS))
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    if log_channel is not None:
        client.set_log_channel(log_channel)

    try:
        client.connect(
            hostname=SSH_HOST,
            port=SSH_PORT,
            username=SSH_USER,
            key_filename=str(SSH_PRIVATE_KEY),
            look_for_keys=False,
            allow_agent=False,
            timeout=timeout,
            banner_timeout=banner_timeout,
            auth_timeout=auth_timeout,
        )
        return client
    except Exception:
        client.close()
        raise


def main():
    client = connect_ssh()

    try:
        print("SSH-подключение установлено")

        stdin, stdout, stderr = client.exec_command(
            "whoami && hostname && cat /etc/os-release"
        )

        output = stdout.read().decode("utf-8")
        errors = stderr.read().decode("utf-8")
        exit_code = stdout.channel.recv_exit_status()

        print(output)
        print(errors)
        print(f"Код завершения: {exit_code}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
