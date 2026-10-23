# 🧊 blkcache

Userspace transparent block device cache.

## ⬇️ Deps

```
sudo apt install libnbd-bin nbdkit-plugin-python nbdfuse fuse3
```

## ℹ️ Usage

```
uvx blkcache /dev/sr0 file.iso
```

Then point tools at `file.iso` instead of `/dev/sr0`.

## How?

It uses `nbdkit` to create a Network Block Storage device in Python, mounts it
using `fuse`, then creates a mmapped disk cache of sectors as they're read.

## Why?

Say you're archiving CDs, DVDs, floppy disks or hard drives that are on their
last legs.

With this you can mount a cached version of the disk in FUSE, read the parts
of the filesystem that are important to you, and dump the contents while
creating a ddrescue image that can be resumed later without unnecessary wear on
the media or waiting days for it to grind against bad blocks. With identical
disks or the same media read in different drives, you can merge ddrescue images
to get a perfect copy.

In my workflow, it's used to speed up imaging disks where I snag the important
before doing a deep copy that might fail later on.

## 🔗 Links

* [🏠 home](https://bitplane.net/dev/python/blkcache)
* [🐱 github](https://github.com/bitplane/blkcache)
* [🐍 pypi](https://pypi.org/project/blkcache)
* [📖 pydoc](https://bitplane.net/dev/python/blkcache/pydoc)

## 🌍 Related

* [🪦 rip](https://github.com/bitplane/rip)
