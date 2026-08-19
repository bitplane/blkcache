from itertools import count

from blkcache import backend


def _context(value):
    yield value


def test_open_does_not_reuse_an_active_handle(monkeypatch):
    contexts = iter((_context("first"), _context("second"), _context("third")))
    monkeypatch.setattr(backend, "TABLE", {})
    monkeypatch.setattr(backend, "HANDLE_IDS", count(1))
    monkeypatch.setattr(backend, "open_file_context", lambda path, mode: next(contexts))
    monkeypatch.setattr(backend, "DEV", object())

    first = backend.open(True)
    second = backend.open(True)
    backend.close(first)
    third = backend.open(True)

    assert (first, second, third) == (1, 2, 3)
    assert backend.TABLE[second][0] == "second"
    assert backend.TABLE[third][0] == "third"
