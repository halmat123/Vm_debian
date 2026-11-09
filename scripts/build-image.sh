
#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

IMAGES_DIR="$PROJECT_DIR/images"
OUTPUT_DIR="$PROJECT_DIR/generated"
BASE_IMAGE="$IMAGES_DIR/debian13-base.qcow2"
WORK_IMAGE="$OUTPUT_DIR/debian13.qcow2"
SEED_IMAGE="$OUTPUT_DIR/seed.iso"
UEFI_VARS="$OUTPUT_DIR/uefi-vars.fd"

DEBIAN_BUILD="20261001-2618"
DEBIAN_FILENAME="debian-13-generic-arm64-$DEBIAN_BUILD.qcow2"
DEBIAN_BASE_URL="https://cloud.debian.org/images/cloud/trixie/$DEBIAN_BUILD"
DEBIAN_URL="$DEBIAN_BASE_URL/$DEBIAN_FILENAME"
DEBIAN_CHECKSUM_URL="$DEBIAN_BASE_URL/SHA512SUMS"
SSH_PUBLIC_KEY="${SSH_PUBLIC_KEY:-$HOME/.ssh/yadro_vm_ed25519.pub}"

QEMU_IMG="${QEMU_IMG:-$HOME/.local/qemu-11.0.5/bin/qemu-img}"
QEMU_VARS_TEMPLATE="${QEMU_VARS_TEMPLATE:-$HOME/.local/qemu-11.0.5/share/qemu/edk2-arm-vars.fd}"

if [[ ! -x "$QEMU_IMG" ]]; then
    QEMU_IMG="$(command -v qemu-img || true)"
fi

if [[ -z "$QEMU_IMG" ]]; then
    echo "Ошибка: qemu-img не найден"
    exit 1
fi

if [[ ! -f "$QEMU_VARS_TEMPLATE" ]]; then
    echo "Ошибка: шаблон UEFI vars не найден: $QEMU_VARS_TEMPLATE"
    exit 1
fi

if [[ ! -s "$SSH_PUBLIC_KEY" ]]; then
    echo "Ошибка: публичный SSH-ключ не найден"
    exit 1
fi

mkdir -p "$IMAGES_DIR" "$OUTPUT_DIR"

if [[ -e "$WORK_IMAGE" || -e "$SEED_IMAGE" || -e "$UEFI_VARS" || -e "$OUTPUT_DIR/cloud-init" ]]; then
    echo "Ошибка: подготовленные файлы уже существуют"
    echo "Существующие файлы не будут перезаписаны"
    exit 1
fi

OPENSSL_BIN="$(command -v openssl)"

if [[ "$(uname -s)" == "Darwin" ]]; then
    OPENSSL_BIN="$(brew --prefix openssl@3)/bin/openssl"
fi

read -rsp "Пароль пользователя debian: " PASSWORD
echo

read -rsp "Повторите пароль: " CONFIRM_PASSWORD
echo

if [[ "$PASSWORD" != "$CONFIRM_PASSWORD" || ${#PASSWORD} -lt 8 ]]; then
    echo "Ошибка: пароли не совпадают или пароль короче 8 символов"
    exit 1
fi

PASSWORD_HASH="$(printf '%s\n' "$PASSWORD" | "$OPENSSL_BIN" passwd -6 -stdin)"

unset PASSWORD CONFIRM_PASSWORD

TEMP_DIR="$(mktemp -d "$OUTPUT_DIR/.build.XXXXXX")"
trap 'rm -rf "$TEMP_DIR"' EXIT

echo "Получение контрольной суммы Debian 13..."
curl -fL --retry 3 "$DEBIAN_CHECKSUM_URL" -o "$TEMP_DIR/SHA512SUMS"

EXPECTED_SHA512="$(awk -v filename="$DEBIAN_FILENAME" '
    {
        name = $2
        sub(/^\*/, "", name)
        if (name == filename) {
            print $1
            exit
        }
    }
' "$TEMP_DIR/SHA512SUMS")"

if [[ -z "$EXPECTED_SHA512" ]]; then
    echo "Ошибка: контрольная сумма для $DEBIAN_FILENAME не найдена"
    exit 1
fi

if [[ -f "$BASE_IMAGE" ]]; then
    IMAGE_TO_VERIFY="$BASE_IMAGE"
else
    echo "Скачивание Debian 13..."
    curl -fL --retry 3 "$DEBIAN_URL" -o "$TEMP_DIR/debian13-base.qcow2"
    IMAGE_TO_VERIFY="$TEMP_DIR/debian13-base.qcow2"
fi

if command -v sha512sum > /dev/null 2>&1; then
    ACTUAL_SHA512="$(sha512sum "$IMAGE_TO_VERIFY" | awk '{print $1}')"
elif command -v shasum > /dev/null 2>&1; then
    ACTUAL_SHA512="$(shasum -a 512 "$IMAGE_TO_VERIFY" | awk '{print $1}')"
else
    echo "Ошибка: не найдена утилита для проверки SHA512"
    exit 1
fi

if [[ "$ACTUAL_SHA512" != "$EXPECTED_SHA512" ]]; then
    echo "Ошибка: контрольная сумма образа Debian не совпала"
    exit 1
fi

"$QEMU_IMG" info "$IMAGE_TO_VERIFY" > /dev/null

if [[ ! -f "$BASE_IMAGE" ]]; then
    mv "$TEMP_DIR/debian13-base.qcow2" "$BASE_IMAGE"
fi

echo "Создание рабочего диска..."
cp "$BASE_IMAGE" "$TEMP_DIR/debian13.qcow2"
"$QEMU_IMG" resize -f qcow2 "$TEMP_DIR/debian13.qcow2" 10G
cp "$QEMU_VARS_TEMPLATE" "$TEMP_DIR/uefi-vars.fd"

mkdir -p "$TEMP_DIR/cloud-init"

cat > "$TEMP_DIR/cloud-init/user-data" <<EOF
#cloud-config
hostname: yadro-vm
users:
  - name: debian
    shell: /bin/bash
    lock_passwd: false
    hashed_passwd: '$PASSWORD_HASH'
    ssh_authorized_keys:
      - $(cat "$SSH_PUBLIC_KEY")
ssh_pwauth: false
EOF

cat > "$TEMP_DIR/cloud-init/meta-data" <<EOF
instance-id: yadro-vm-001
local-hostname: yadro-vm
EOF

chmod 600 "$TEMP_DIR/cloud-init/user-data"

echo "Создание ISO с настройками SSH..."

if [[ "$(uname -s)" == "Darwin" ]]; then
    hdiutil makehybrid -o "$TEMP_DIR/seed.iso" "$TEMP_DIR/cloud-init" -iso -joliet -default-volume-name cidata
else
    if ! command -v genisoimage > /dev/null; then
        echo "Ошибка: необходимо установить genisoimage"
        exit 1
    fi

    genisoimage -quiet -o "$TEMP_DIR/seed.iso" -V cidata -J -r -graft-points \
        "user-data=$TEMP_DIR/cloud-init/user-data" \
        "meta-data=$TEMP_DIR/cloud-init/meta-data"
fi

mv "$TEMP_DIR/debian13.qcow2" "$WORK_IMAGE"
mv "$TEMP_DIR/seed.iso" "$SEED_IMAGE"
mv "$TEMP_DIR/uefi-vars.fd" "$UEFI_VARS"
mv "$TEMP_DIR/cloud-init" "$OUTPUT_DIR/cloud-init"

echo "Образ Debian 13 успешно подготовлен"
echo "Виртуальный диск: $WORK_IMAGE"
echo "ISO с настройками: $SEED_IMAGE"
echo "UEFI vars: $UEFI_VARS"
