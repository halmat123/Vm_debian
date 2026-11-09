import os
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
CONTAINERIZED = os.getenv("YADRO_CONTAINER", "0") == "1"


def env_path(name, default):
    return Path(os.getenv(name, str(default))).expanduser()


def env_int(name, default):
    return int(os.getenv(name, str(default)))


DATA_DIR = env_path("VM_DATA_DIR", PROJECT_DIR / "generated")
RUNTIME_DIR = env_path("VM_RUNTIME_DIR", DATA_DIR)

QEMU_BINARY = env_path(
    "QEMU_BINARY",
    Path.home() / ".local/qemu-11.0.5/bin/qemu-system-aarch64",
)
QEMU_IMG = env_path(
    "QEMU_IMG",
    Path.home() / ".local/qemu-11.0.5/bin/qemu-img",
)
QEMU_FIRMWARE = env_path(
    "QEMU_FIRMWARE",
    Path.home() / ".local/qemu-11.0.5/share/qemu/edk2-aarch64-code.fd",
)
QEMU_VARS_TEMPLATE = env_path(
    "QEMU_VARS_TEMPLATE",
    Path.home() / ".local/qemu-11.0.5/share/qemu/edk2-arm-vars.fd",
)

DISK = DATA_DIR / "debian13.qcow2"
SEED = DATA_DIR / "seed.iso"
UEFI_VARS = DATA_DIR / "uefi-vars.fd"
QEMU_LOG = DATA_DIR / "qemu.log"
READY_MARKER = DATA_DIR / ".ready"

QMP_SOCKET = RUNTIME_DIR / "qmp.sock"
SERIAL_SOCKET = RUNTIME_DIR / "serial.sock"

SSH_PRIVATE_KEY = env_path(
    "SSH_PRIVATE_KEY",
    Path.home() / ".ssh/yadro_vm_ed25519",
)
SSH_KNOWN_HOSTS = env_path(
    "SSH_KNOWN_HOSTS",
    Path.home() / ".ssh/known_hosts",
)
SSH_TRUST_ON_FIRST_USE = os.getenv(
    "SSH_TRUST_ON_FIRST_USE",
    "1" if CONTAINERIZED else "0",
) == "1"
SSH_HOST = os.getenv("SSH_HOST", "127.0.0.1")
SSH_PORT = env_int("SSH_PORT", 2222)
SSH_USER = os.getenv("SSH_USER", "debian")

VM_ACCEL = os.getenv("VM_ACCEL", "hvf")
VM_CPU = os.getenv("VM_CPU", "host")
VM_CPUS = env_int("VM_CPUS", 2)
VM_MEMORY_MB = env_int("VM_MEMORY_MB", 2048)
VM_STOP_TIMEOUT = env_int("VM_STOP_TIMEOUT", 60)
VM_START_TIMEOUT = env_int("VM_START_TIMEOUT", 10)
