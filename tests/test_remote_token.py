import json

import pytest

from floorplan import remote


def _fake_cli(tokens):
    """A `kaggle datasets download` that writes jobs.json with the next token in `tokens`."""

    def cli(_cli, *args, check=True):
        out = args[args.index("-p") + 1]
        with open(f"{out}/jobs.json", "w") as f:
            json.dump({"token": tokens.pop(0) if len(tokens) > 1 else tokens[0]}, f)
        return 0, ""

    return cli


def test_await_token_waits_for_the_new_version(monkeypatch, tmp_path):
    monkeypatch.setattr(remote, "_cli", _fake_cli(["old", "old", "new"]))
    monkeypatch.setattr(remote.time, "sleep", lambda _: None)
    remote._await_token(["kaggle"], "u/d", "new", tmp_path / "c", "uploaded")


def test_await_token_raises_when_the_upload_never_lands(monkeypatch, tmp_path):
    monkeypatch.setattr(remote, "_cli", _fake_cli(["old"]))
    monkeypatch.setattr(remote, "DATASET_VISIBLE_MIN", 0)
    monkeypatch.setattr(remote.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="still holds run old, not new"):
        remote._await_token(["kaggle"], "u/d", "new", tmp_path / "c", "silent failure")
