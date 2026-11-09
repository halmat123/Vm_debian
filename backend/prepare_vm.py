import hashlib
import os
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from config import (
    DATA_DIR,
    DISK,
    QEMU_FIRMWARE,
    QEMU_IMG,
    QEMU_VARS_TEMPLATE,
    READY_MARKER,
    SEED,
    SSH_KNOWN_HOSTS,
    SSH_PRIVATE_KEY,
    UEFI_VARS,
)


DEBIAN_BUILD = "20261001-2618"
DEBIAN_FILENAME = f"debian-13-generic-arm64-{DEBIAN_BUILD}.qcow2"
DEBIAN_BASE_URL = (
    f"https://cloud.debian.org/images/cloud/trixie/{DEBIAN_BUILD}"
)
DEBIAN_IMAGE_URL = f"{DEBIAN_BASE_URL}/{DEBIAN_FILENAME}"
DEBIAN_CHECKSUM_URL = f"{DEBIAN_BASE_URL}/SHA512SUMS"
BASE_IMAGE = DATA_DIR / "debian13-base.qcow2"
TEMPLATE_DIR = Path(__file__).resolve().parent / "cloud-init"


def fetch(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "yadro-vm-manager/1.0"},
    )
    return urllib.request.urlopen(request, timeout=60)


def expected_sha512():
    with fetch(DEBIAN_CHECKSUM_URL) as response:
        manifest = response.read().decode("utf-8")

    for line in manifest.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == DEBIAN_FILENAME:
            return parts[0].lower()

    raise RuntimeError(
        f"В SHA512SUMS не найден образ {DEBIAN_FILENAME}"
    )


def sha512(path):
    digest = hashlib.sha512()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def download_base_image():
    expected = expected_sha512()

    if BASE_IMAGE.is_file() and sha512(BASE_IMAGE) == expected:
        return

    partial = BASE_IMAGE.with_suffix(".qcow2.part")
    partial.unlink(missing_ok=True)

    print("Скачивание закреплённого образа Debian 13 ARM64...", flush=True)
    try:
        with fetch(DEBIAN_IMAGE_URL) as response, partial.open("wb") as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)

        actual = sha512(partial)
        if actual != expected:
            raise RuntimeError("Контрольная сумма образа Debian не совпала")

        os.replace(partial, BASE_IMAGE)
    finally:
        partial.unlink(missing_ok=True)


def validate_ready_state():
    required = (
        DISK,
        SEED,
        UEFI_VARS,
        SSH_PRIVATE_KEY,
        Path(str(SSH_PRIVATE_KEY) + ".pub"),
        SSH_KNOWN_HOSTS,
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError(
            "Состояние VM помечено готовым, но отсутствуют файлы: "
            + ", ".join(missing)
        )


def prepare():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if READY_MARKER.is_file():
        validate_ready_state()
        print("Подготовленное состояние Debian найдено в Docker volume", flush=True)
        return

    existing = [str(path) for path in (DISK, SEED, UEFI_VARS)
                if path.exists() or path.is_symlink()]
    if existing:
        raise RuntimeError(
            "Найдены файлы VM без маркера готовности. Они сохранены; "
            "проверьте существующее состояние перед подготовкой: "
            + ", ".join(existing)
        )

    for path in (QEMU_IMG, QEMU_FIRMWARE, QEMU_VARS_TEMPLATE):
        if not path.is_file():
            raise FileNotFoundError(f"Не найден необходимый файл: {path}")

    download_base_image()

    with tempfile.TemporaryDirectory(prefix=".prepare-", dir=DATA_DIR) as temp_name:
        temp = Path(temp_name)
        temp_disk = temp / DISK.name
        temp_seed = temp / SEED.name
        temp_vars = temp / UEFI_VARS.name
        temp_ssh = temp / "ssh"
        temp_cloud_init = temp / "cloud-init"
        temp_ssh.mkdir()
        temp_cloud_init.mkdir()

        print("Создание рабочего диска Debian...", flush=True)
        shutil.copyfile(BASE_IMAGE, temp_disk)
        subprocess.run(
            [str(QEMU_IMG), "resize", "-f", "qcow2", str(temp_disk), "10G"],
            check=True,
        )

        private_key = temp_ssh / SSH_PRIVATE_KEY.name
        public_key_path = Path(str(SSH_PRIVATE_KEY) + ".pub")
        new_key = not SSH_PRIVATE_KEY.exists()
        if new_key:
            if SSH_PRIVATE_KEY.is_symlink() or public_key_path.exists() or public_key_path.is_symlink():
                raise RuntimeError("Нельзя создавать ключ поверх существующих файлов SSH")
            subprocess.run(
                ["ssh-keygen", "-q", "-t", "ed25519", "-N", "",
                 "-C", "yadro-vm-runtime", "-f", str(private_key)],
                check=True,
            )
            os.chmod(private_key, 0o600)
            public_key = Path(str(private_key) + ".pub").read_text()
        else:
            public_key = subprocess.run(
                ["ssh-keygen", "-y", "-P", "", "-f", str(SSH_PRIVATE_KEY)],
                check=True, capture_output=True, text=True,
            ).stdout
            if public_key_path.exists():
                if public_key_path.read_text().split()[:2] != public_key.split()[:2]:
                    raise RuntimeError("Публичный ключ не соответствует приватному")

        user_data = (TEMPLATE_DIR / "user-data.tmpl").read_text()
        user_data = user_data.replace(
            "__SSH_PUBLIC_KEY__",
            public_key.strip(),
        )
        (temp_cloud_init / "user-data").write_text(user_data)
        shutil.copyfile(
            TEMPLATE_DIR / "meta-data",
            temp_cloud_init / "meta-data",
        )

        subprocess.run(
            [
                "genisoimage",
                "-quiet",
                "-output",
                str(temp_seed),
                "-volid",
                "cidata",
                "-joliet",
                "-rock",
                "-graft-points",
                "user-data=" + str(temp_cloud_init / "user-data"),
                "meta-data=" + str(temp_cloud_init / "meta-data"),
            ],
            check=True,
        )

        shutil.copyfile(QEMU_VARS_TEMPLATE, temp_vars)
        SSH_PRIVATE_KEY.parent.mkdir(parents=True, exist_ok=True)
        if new_key:
            with SSH_PRIVATE_KEY.open("xb") as output:
                os.chmod(SSH_PRIVATE_KEY, 0o600)
                output.write(private_key.read_bytes())
        if not public_key_path.exists():
            with public_key_path.open("x") as output:
                output.write(public_key)
        SSH_KNOWN_HOSTS.parent.mkdir(parents=True, exist_ok=True)
        if not SSH_KNOWN_HOSTS.exists():
            SSH_KNOWN_HOSTS.touch(mode=0o600, exist_ok=False)

        os.replace(temp_disk, DISK)
        os.replace(temp_seed, SEED)
        os.replace(temp_vars, UEFI_VARS)

    READY_MARKER.write_text(
        f"Debian image: {DEBIAN_FILENAME}\nQEMU firmware: {QEMU_FIRMWARE.name}\n"
    )
    BASE_IMAGE.unlink(missing_ok=True)
    print("Состояние Debian успешно подготовлено", flush=True)


if __name__ == "__main__":
    prepare()
