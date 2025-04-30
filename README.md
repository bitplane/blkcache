# 🧊 blkcache

Userspace transparent block device cache

## Deps

```
sudo apt install libndb-bin nbdkit-plugin-python nbdfuse fuse3
```

## Usage

```
uvx blkcache /dev/sr0 file.iso
```

Then point tools at `file.iso` instead of `/dev/sr0`.

## Why?

Copying some CDs and needed a way to do `7z /dev/sr0` to dump the filesystem,
and then `ddrescue /dev/sr0` to get the image if possible. This means it
doesn't have to read the disk twice

## How?

mind your own fucking business
