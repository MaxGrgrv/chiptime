"""F24: interval/structure detection — evidence ladder, bands, honesty."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from chiptime import metrics
from chiptime.message import FieldValue, Message
from chiptime.model import Length, Records, Session, Stream

BASE = datetime(2026, 6, 1, 8, 0, 0, tzinfo=UTC)


def _session(sport: str, sub: str | None = None, **streams: list[object]) -> Session:
    n = max((len(v) for v in streams.values()), default=0)
    rec = Records(
        time=[BASE + timedelta(seconds=i) for i in range(n)],
        streams={k: Stream(k, None, list(v)) for k, v in streams.items()},
    )
    return Session(
        sport=sport, sub_sport=sub, start_time=BASE if n else None, end_time=None, records=rec
    )


def _square_power(reps: int, work_s: int, rec_s: int, hi: float, lo: float) -> list[object]:
    out: list[object] = [float(lo)] * 60  # warm-in
    for _ in range(reps):
        out += [float(hi)] * work_s + [float(lo)] * rec_s
    return out


def _lap_msg(
    start_offset_s: float, elapsed_s: float, trigger: str | None, step_idx: int | None = None
) -> Message:
    fields = {
        "start_time": FieldValue(BASE + timedelta(seconds=start_offset_s)),
        "total_elapsed_time": FieldValue(elapsed_s),
        "total_timer_time": FieldValue(elapsed_s),
    }
    if trigger is not None:
        fields["lap_trigger"] = FieldValue(trigger)
    if step_idx is not None:
        fields["wkt_step_index"] = FieldValue(step_idx)
    return Message(global_num=19, name="lap", local_id=0, byte_offset=0, fields=fields)


# --- detection ----------------------------------------------------------


def test_detects_erg_square_wave() -> None:
    s = _session("cycling", power=_square_power(6, 30, 30, 300.0, 120.0))
    st = metrics.detect_structure(s)
    assert st.basis == "detected:power-steps"
    work = [iv for iv in st.intervals if iv.kind == "work"]
    assert len(work) == 6
    assert all(iv.avg_primary is not None and iv.avg_primary > 280 for iv in work)
    assert len(st.repeats) == 1
    g = st.repeats[0]
    assert g.count == 6 and g.label.startswith("6 x 0:")
    assert g.mean_primary is not None and abs(g.mean_primary - 300.0) < 5
    assert "@ 300 W" in g.label
    # determinism: identical rerun -> identical result
    assert metrics.detect_structure(s) == st


def test_declines_irregular_efforts() -> None:
    vals: list[object] = [100.0] * 60
    for dur in (30, 300, 45, 700):  # wildly varied "efforts"
        vals += [280.0] * dur + [100.0] * 120
    st = metrics.detect_structure(_session("cycling", power=vals))
    assert st.basis == "none" and st.note is not None


def test_declines_too_few_reps() -> None:
    s = _session("cycling", power=_square_power(2, 60, 60, 300.0, 100.0))
    st = metrics.detect_structure(s)
    assert st.basis == "none"
    assert st.note is not None and "2 work" in st.note


def test_run_uses_speed_steps() -> None:
    vals: list[object] = [2.8] * 60
    for _ in range(4):
        vals += [4.5] * 60 + [2.5] * 45
    st = metrics.detect_structure(_session("running", enhanced_speed=vals))
    assert st.basis == "detected:speed-steps"
    assert len([iv for iv in st.intervals if iv.kind == "work"]) == 4
    assert st.repeats and "@ " in st.repeats[0].label  # pace label, e.g. @ 3:42/km


def test_no_streams_is_honest() -> None:
    st = metrics.detect_structure(_session("cycling"))
    assert st.basis == "none" and st.intervals == ()


# --- laps & workout steps ----------------------------------------------


def test_manual_laps_route_and_classify() -> None:
    power = _square_power(3, 120, 120, 320.0, 110.0)
    s = _session("cycling", power=power)
    # laps alternate exactly with the square wave: work at 60, rec at 180, ...
    msgs = []
    off = 60.0
    for _ in range(6):
        msgs.append(_lap_msg(off, 120.0, "manual"))
        off += 120.0
    st = metrics.detect_structure(s, msgs)
    assert st.basis == "laps:manual"
    kinds = [iv.kind for iv in st.intervals]
    assert kinds == ["work", "recovery", "work", "recovery", "work", "recovery"]
    assert len(st.repeats) == 1 and st.repeats[0].count == 3
    assert st.repeats[0].mean_rest_s is not None


def test_single_manual_lap_falls_through_to_detection() -> None:
    s = _session("cycling", power=_square_power(4, 40, 40, 310.0, 90.0))
    st = metrics.detect_structure(s, [_lap_msg(0, 380.0, "manual")])
    assert st.basis == "detected:power-steps"


def test_auto_laps_are_not_structure() -> None:
    s = _session("cycling", power=_square_power(4, 40, 40, 310.0, 90.0))
    msgs = [_lap_msg(i * 95.0, 95.0, "distance") for i in range(4)]
    st = metrics.detect_structure(s, msgs)
    assert st.basis == "detected:power-steps"


def test_workout_steps_use_step_intensity() -> None:
    s = _session("running", enhanced_speed=[3.0] * 600)
    steps = []
    for idx, intensity in enumerate(("warmup", "active", "rest", "active", "cooldown")):
        steps.append(
            Message(
                global_num=27,
                name="workout_step",
                local_id=0,
                byte_offset=0,
                fields={"message_index": FieldValue(idx), "intensity": FieldValue(intensity)},
            )
        )
    laps = [_lap_msg(i * 120.0, 120.0, "time", step_idx=i) for i in range(5)]
    st = metrics.detect_structure(s, steps + laps)
    assert st.basis == "steps:workout"
    assert [iv.kind for iv in st.intervals] == ["warmup", "work", "rest", "work", "cooldown"]
    assert [iv.step_index for iv in st.intervals] == [0, 1, 2, 3, 4]


# --- swim sets ----------------------------------------------------------


def _length(i: int, t0: float, dur: float, kind: str = "active") -> Length:
    start = BASE + timedelta(seconds=t0)
    return Length(
        start_time=start,
        end_time=start + timedelta(seconds=dur),
        length_type=kind,
        swim_stroke="freestyle",
        total_strokes=18,
        total_elapsed_time_s=dur,
    )


def test_swim_sets_group_lengths() -> None:
    # 4 x 100m (4 lengths of 25m each, continuous) with 20 s wall rest
    lengths: list[Length] = []
    t = 0.0
    for _rep in range(4):
        for _l in range(4):
            lengths.append(_length(len(lengths), t, 26.0))
            t += 26.0 + 1.0  # 1 s turn, below SWIM_SET_REST_MIN_S -> same swim
        t += 20.0  # wall rest -> set boundary
    s = _session("swimming", "lap_swimming")
    s.lengths = lengths
    msg = Message(
        global_num=18,
        name="session",
        local_id=0,
        byte_offset=0,
        fields={"pool_length": FieldValue(25.0)},
    )
    st = metrics.detect_structure(s, [msg])
    assert st.basis == "lengths:sets"
    assert len(st.intervals) == 4
    assert all(iv.lengths == 4 and iv.distance_m == 100.0 for iv in st.intervals)
    assert len(st.repeats) == 1
    assert st.repeats[0].count == 4 and st.repeats[0].label.startswith("4 x 100m @ 1:4")
