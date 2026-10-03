import json

from floorplan.cli import main


def test_run_writes_plan_json_for_a_stray_capture(stray_capture, tmp_path, capsys):
    out = tmp_path / "outputs"
    assert main(["run", str(stray_capture), "--out", str(out)]) == 0
    plan = json.loads((out / "stray01_lidar" / "plan.json").read_text())
    assert plan["capture"] == {
        "id": "stray01",
        "tier": "lidar",
        "source": str(stray_capture),
        "device": None,
    }
    assert "load" in plan["timing_s"]
    assert (out / "stray01_lidar" / "plan.png").exists()
    assert "plan.json" in capsys.readouterr().out


def test_lidar_run_without_walls_warns_instead_of_crashing(stray_capture, tmp_path):
    out = tmp_path / "outputs"
    assert main(["run", str(stray_capture), "--out", str(out)]) == 0
    plan = json.loads((out / "stray01_lidar" / "plan.json").read_text())
    assert plan["rooms"] == []
    assert any("no rooms" in w for w in plan["warnings"])


def test_run_honours_explicit_tier(stray_capture, tmp_path, monkeypatch):
    # the video stage itself (ffmpeg + model) is exercised on real captures, not here
    from floorplan import pipeline
    from floorplan.output import Result

    seen = {}

    def fake_video(path, capture, n_frames, up):
        seen["path"] = path
        return Result(capture=capture, rooms=[])

    monkeypatch.setattr(pipeline, "_run_video", fake_video)
    out = tmp_path / "outputs"
    assert main(["run", str(stray_capture), "--tier", "video", "--out", str(out)]) == 0
    plan = json.loads((out / "stray01_video" / "plan.json").read_text())
    assert plan["capture"]["tier"] == "video"
    assert seen["path"] == stray_capture


def test_run_reports_bad_input_without_traceback(tmp_path, capsys):
    assert main(["run", str(tmp_path)]) == 2
    assert "not a recognised capture" in capsys.readouterr().err
