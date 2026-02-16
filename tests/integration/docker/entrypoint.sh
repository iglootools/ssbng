#!/bin/bash
set -e

# Set up authorized keys from mounted file
if [ -f /tmp/authorized_keys ]; then
    cp /tmp/authorized_keys /home/testuser/.ssh/authorized_keys
    chmod 600 /home/testuser/.ssh/authorized_keys
    chown testuser:testuser /home/testuser/.ssh/authorized_keys
fi

# Create btrfs filesystem on a file-backed image
truncate -s 512M /var/btrfs.img
mkfs.btrfs -f /var/btrfs.img
mkdir -p /mnt/btrfs
mount /var/btrfs.img /mnt/btrfs

# Create directory structures
mkdir -p /data/src /data/latest
mkdir -p /mnt/btrfs/src

# Set ownership
chown -R testuser:testuser /data
chown -R testuser:testuser /mnt/btrfs

# Generate SSH host keys if not present
ssh-keygen -A

# Start sshd in foreground
exec /usr/sbin/sshd -D -e
