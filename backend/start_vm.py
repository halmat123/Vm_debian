import subprocess

from config import (
    DATA_DIR,
    DISK,
    QEMU_BINARY,
    QEMU_FIRMWARE,
    QMP_SOCKET,
    RUNTIME_DIR,
    SEED,
    SERIAL_SOCKET,
    UEFI_VARS,
    VM_ACCEL,
    VM_CPU,
    VM_CPUS,
    VM_MEMORY_MB,
)


def build_command():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    for path in [QEMU_BINARY, QEMU_FIRMWARE, DISK, SEED, UEFI_VARS]:
        if not path.is_file():
            raise FileNotFoundError(f"Файл не найден: {path}")

    command = [
        str(QEMU_BINARY),
        "-machine", "virt",
        "-accel", VM_ACCEL,
        "-cpu", VM_CPU,
        "-smp", str(VM_CPUS),
        "-m", str(VM_MEMORY_MB),
        "-drive", f"if=pflash,format=raw,readonly=on,file={QEMU_FIRMWARE}",
        "-drive", f"if=pflash,format=raw,file={UEFI_VARS}",
        "-drive", f"if=virtio,format=qcow2,file={DISK}",
        "-drive", f"if=virtio,format=raw,readonly=on,file={SEED}",
        "-netdev", "user,id=net0,hostfwd=tcp:127.0.0.1:2222-:22",
        "-device", "virtio-net-pci,netdev=net0,romfile=",
        "-display", "none",
        "-monitor", "none",
        "-qmp", f"unix:{QMP_SOCKET},server=on,wait=off",
        "-serial", f"unix:{SERIAL_SOCKET},server=on,wait=off",
    ]

    return command


def main():
    print(f"Запуск QEMU 11.0.5 с ускорителем {VM_ACCEL}...", flush=True)
    subprocess.run(build_command(), check=True)


if __name__ == "__main__":
    main()
