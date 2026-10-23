import errno
from io import StringIO
from pathlib import Path

import pytest

from blkcache.ddrescue import load, save
from blkcache.file.base import File
from blkcache.file.cached import CachedFile
from blkcache.file.filemap import STATUS_ERROR, STATUS_OK, STATUS_UNTRIED, FileMap


class CountingFile(File):
    def __init__(self, path: Path, mode: str):
        super().__init__(path, mode)
        self.reads = []

    def pread(self, count: int, offset: int) -> bytes:
        self.reads.append((count, offset))
        return super().pread(count, offset)


class BrokenFile(CountingFile):
    def pread(self, count: int, offset: int) -> bytes:
        self.reads.append((count, offset))
        raise OSError("unreadable medium")


class SelectivelyBrokenFile(CountingFile):
    def pread(self, count: int, offset: int) -> bytes:
        if offset < 4:
            raise OSError("cached prefix must not be reread")
        return super().pread(count, offset)


def test_cache_miss_populates_cache_and_map(tmp_path):
    source_path = tmp_path / "source"
    cache_path = tmp_path / "cache"
    source_path.write_bytes(b"abcdefgh")
    cache_path.write_bytes(b"\0" * 8)
    source = CountingFile(source_path, "rb")
    filemap = FileMap(8)
    saves = []

    with CachedFile(source, File(cache_path, "r+b"), filemap, lambda: saves.append(True)) as cached:
        assert cached.pread(4, 2) == b"cdef"

    assert source.reads == [(4, 2)]
    assert cache_path.read_bytes() == b"\0\0cdef\0\0"
    assert filemap[1] == STATUS_UNTRIED
    assert filemap[2] == STATUS_OK
    assert filemap[5] == STATUS_OK
    assert filemap[6] == STATUS_UNTRIED
    assert saves == [True]


def test_cached_range_is_reused_without_reading_backing_file(tmp_path):
    source_path = tmp_path / "source"
    cache_path = tmp_path / "cache"
    source_path.write_bytes(b"physical")
    cache_path.write_bytes(b"cached!!")
    filemap = FileMap(8)
    filemap[:] = STATUS_OK

    with CachedFile(BrokenFile(source_path, "rb"), File(cache_path, "r+b"), filemap) as cached:
        assert cached.pread(8, 0) == b"cached!!"


def test_preallocated_zeroes_are_not_a_cache_hit(tmp_path):
    source_path = tmp_path / "source"
    cache_path = tmp_path / "cache"
    source_path.write_bytes(b"original")
    cache_path.write_bytes(b"\0" * 8)

    with CachedFile(File(source_path, "rb"), File(cache_path, "r+b"), FileMap(8)) as cached:
        assert cached.pread(8, 0) == b"original"


def test_read_error_is_recorded_and_reraised(tmp_path):
    source_path = tmp_path / "source"
    cache_path = tmp_path / "cache"
    source_path.write_bytes(b"physical")
    cache_path.write_bytes(b"\0" * 8)
    filemap = FileMap(8)
    saves = []

    with (
        CachedFile(
            BrokenFile(source_path, "rb"), File(cache_path, "r+b"), filemap, lambda: saves.append(True)
        ) as cached,
        pytest.raises(OSError, match="unreadable medium"),
    ):
        cached.pread(4, 2)

    assert filemap[2] == STATUS_ERROR
    assert filemap[5] == STATUS_ERROR
    assert saves == [True]


def test_mixed_read_uses_cache_and_only_fetches_missing_ranges(tmp_path):
    source_path = tmp_path / "source"
    cache_path = tmp_path / "cache"
    source_path.write_bytes(b"abcdefgh")
    cache_path.write_bytes(b"ABCD\0\0\0\0")
    source = SelectivelyBrokenFile(source_path, "rb")
    filemap = FileMap(8)
    filemap[0:4] = STATUS_OK

    with CachedFile(source, File(cache_path, "r+b"), filemap) as cached:
        assert cached.pread(8, 0) == b"ABCDefgh"

    assert source.reads == [(4, 4)]
    assert cache_path.read_bytes() == b"ABCDefgh"
    assert filemap[0] == STATUS_OK
    assert filemap[7] == STATUS_OK


def test_mixed_read_error_preserves_cached_range(tmp_path):
    source_path = tmp_path / "source"
    cache_path = tmp_path / "cache"
    source_path.write_bytes(b"abcdefgh")
    cache_path.write_bytes(b"ABCD\0\0\0\0")
    filemap = FileMap(8)
    filemap[0:4] = STATUS_OK

    with (
        CachedFile(BrokenFile(source_path, "rb"), File(cache_path, "r+b"), filemap) as cached,
        pytest.raises(OSError, match="unreadable medium"),
    ):
        cached.pread(8, 0)

    assert filemap[0] == STATUS_OK
    assert filemap[3] == STATUS_OK
    assert filemap[4] == STATUS_ERROR
    assert filemap[7] == STATUS_ERROR


def test_failed_read_is_not_retried_even_after_reopening(tmp_path):
    source_path = tmp_path / "source"
    cache_path = tmp_path / "cache"
    source_path.write_bytes(b"abcdefgh")
    cache_path.write_bytes(b"\0" * 8)
    source = BrokenFile(source_path, "rb")
    filemap = FileMap(8)
    saved_map = StringIO()

    with CachedFile(source, File(cache_path, "r+b"), filemap, lambda: save(saved_map, [], filemap, {})) as cached:
        with pytest.raises(OSError, match="unreadable medium"):
            cached.pread(4, 2)
        for count, offset in [(4, 2), (1, 3), (8, 0)]:
            with pytest.raises(OSError) as error:
                cached.pread(count, offset)
            assert error.value.errno == errno.EIO

    assert source.reads == [(4, 2)]

    # A fresh handle must also respect errors persisted by the first handle.
    restored_map = FileMap(8)
    saved_map.seek(0)
    load(saved_map, [], restored_map, {})
    source = CountingFile(source_path, "rb")
    with CachedFile(source, File(cache_path, "r+b"), restored_map) as cached:
        with pytest.raises(OSError) as error:
            cached.pread(4, 2)
        assert error.value.errno == errno.EIO
        assert source.reads == []
        # Untouched regions can still be recovered and then read from cache.
        assert cached.pread(2, 0) == b"ab"
        assert cached.pread(2, 6) == b"gh"
        assert cached.pread(2, 0) == b"ab"
        assert cached.pread(2, 6) == b"gh"
    assert source.reads == [(2, 0), (2, 6)]


@pytest.mark.parametrize("status", ["-", "*", "/"])
@pytest.mark.parametrize("bad_offset", [0, 3, 7])
def test_known_failure_rejects_entire_request_without_io(tmp_path, status, bad_offset):
    source_path = tmp_path / "source"
    cache_path = tmp_path / "cache"
    source_path.write_bytes(b"abcdefgh")
    cache_path.write_bytes(b"CACHED!!")
    source = CountingFile(source_path, "rb")
    cache = CountingFile(cache_path, "r+b")
    filemap = FileMap(8)
    filemap[1:3] = STATUS_OK
    filemap[bad_offset] = status
    original_transitions = filemap.transitions.copy()
    saves = []

    with CachedFile(source, cache, filemap, lambda: saves.append(True)) as cached:
        with pytest.raises(OSError) as error:
            cached.pread(8, 0)
        assert error.value.errno == errno.EIO
        assert source.reads == []
        assert cache.reads == []
        assert filemap.transitions == original_transitions
        assert saves == []
        # A neighboring good range remains usable despite the failed request.
        assert cached.pread(2, 1) == b"AC"
        assert source.reads == []
