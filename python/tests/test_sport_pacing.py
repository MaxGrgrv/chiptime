"""F23: sport profiles, pacing math, distance splits, zone ladder."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from chiptime import metrics
from chiptime.message import FieldValue, Message
from chiptime.model import Records, Session, Stream, Totals


def _session(sport: str, sub: str | None = None, **streams: list[object]) -> Session:
    n = max((len(v) for v in streams.values()), default=0)
    base = datetime(2026, 6, 1, 8, 0, 0, tzinfo=UTC)
    rec = Records(
        time=[base + timedelta(seconds=i) for i in range(n)],
        streams={k: Stream(k, None, list(v)) for k, v in streams.items()},
    )
    return Session(
        sport=sport, sub_sport=sub, start_time=base if n else None, end_time=None, records=rec
    )


# --- profiles -----------------------------------------------------------


def test_profile_resolution() -> None:
    assert metrics.profile_for(_session("running")).pace_style == "per_km"
    assert metrics.profile_for(_session("cycling")).primary == "power"
    pool = metrics.profile_for(_session("swimming", "lap_swimming"))
    assert pool.pace_style == "per_100m" and pool.distance_from_lengths
    ow = metrics.profile_for(_session("swimming", "open_water"))
    assert ow.key == "open_water_swim" and not ow.distance_from_lengths
    assert metrics.profile_for(_session("rowing")).pace_style == "per_500m"
    assert metrics.profile_for(_session("fitness_equipment", "indoor_rowing")).key == "rowing"
    assert metrics.profile_for(_session("kitesurfing")).key == "generic"


def test_primary_signal_prefers_power_only_when_present() -> None:
    ride = _session("cycling", power=[210, 215, None], speed=[8.0, 8.1, 8.2])
    assert metrics.primary_signal(ride) == ("power", "power")
    ride_np = _session("cycling", speed=[8.0, 8.1, 8.2])
    assert metrics.primary_signal(ride_np) == ("speed", "speed")
    run = _session("running", enhanced_speed=[3.0, 3.1], speed=[3.0, 3.1])
    assert metrics.primary_signal(run) == ("speed", "enhanced_speed")
    assert metrics.primary_signal(_session("running")) == ("none", None)


def test_cadence_display_doubles_per_leg_runs_labeled() -> None:
    run = metrics.profile_for(_session("running"))
    val, units, note = metrics.cadence_display(87.0, run)
    assert (val, units, note) == (174.0, "spm", "doubled_per_leg_cadence")
    val, _, note = metrics.cadence_display(172.0, run)  # already steps/min
    assert (val, note) == (172.0, None)
    ride = metrics.profile_for(_session("cycling"))
    assert metrics.cadence_display(85.0, ride) == (85.0, "rpm", None)
    assert metrics.cadence_display(None, ride) == (None, "rpm", None)


# --- pace math ----------------------------------------------------------


def test_pace_seconds_and_inverse() -> None:
    assert metrics.pace_seconds(1000.0 / 259.5, "per_km") is not None
    assert abs(metrics.pace_seconds(1000.0 / 259.5, "per_km") - 259.5) < 1e-9
    assert metrics.pace_seconds(0.0, "per_km") is None  # standstill: undefined
    assert metrics.pace_seconds(None, "per_100m") is None
    assert metrics.pace_seconds(4.0, "speed") is None
    assert abs(metrics.speed_from_pace(300.0, "per_km") - 1000.0 / 300.0) < 1e-12


def test_format_pace_exact() -> None:
    assert metrics.format_pace(259.5, "per_km") == "4:20"
    assert metrics.format_pace(259.4, "per_km") == "4:19"
    assert metrics.format_pace(105.0, "per_100m", suffix=True) == "1:45/100m"
    assert metrics.format_pace(112.53, "per_500m") == "1:52.5"
    assert metrics.format_pace(112.55, "per_500m", suffix=True) == "1:52.6/500m"
    assert metrics.format_pace(None, "per_km") is None
    assert metrics.format_speed_kmh(9.0, suffix=True) == "32.4 km/h"


def test_concept2_round_trip() -> None:
    for watts in (75.0, 150.0, 200.0, 350.0):
        split = metrics.watts_to_split_500m(watts)
        assert abs(metrics.split_500m_to_watts(split) - watts) < 0.1
    # published anchor: 2:00/500m == 2.80/(0.24^3) ≈ 202.5 W
    assert abs(metrics.split_500m_to_watts(120.0) - 202.546) < 0.01


# --- splits -------------------------------------------------------------


def test_distance_splits_constant_speed() -> None:
    # 2.5 km at exactly 4:00/km (4.1667 m/s), 1 Hz
    n = 601
    speed = 1000.0 / 240.0
    s = _session(
        "running",
        distance=[i * speed for i in range(n)],
        heart_rate=[150 + (i % 3) for i in range(n)],
    )
    splits = metrics.distance_splits(s, 1000.0)
    assert [round(x.duration_s, 3) for x in splits] == [240.0, 240.0, 120.0]
    assert [x.partial for x in splits] == [False, False, True]
    assert [metrics.format_pace(x.pace_s, "per_km") for x in splits] == ["4:00", "4:00", "4:00"]
    assert splits[0].start_m == 0.0 and splits[0].end_m == 1000.0
    assert splits[2].end_m == 2500.0
    assert splits[0].avg_hr is not None and 150 <= splits[0].avg_hr <= 152
    assert splits[0].avg_power is None  # no power stream: None, not 0
    assert splits[0].ascent_m is None  # no altitude stream


def test_distance_splits_interpolates_and_counts_ascent() -> None:
    # 10 m/s with a 2-sample gap in distance presence and rising altitude
    s = _session(
        "cycling",
        distance=[0.0, 10.0, None, 30.0, 40.0, 50.0],
        altitude=[100.0, 101.0, 102.0, 101.0, 103.0, 104.0],
    )
    splits = metrics.distance_splits(s, 25.0)
    assert len(splits) == 2
    first = splits[0]
    assert first.end_m == 25.0 and abs(first.duration_s - 2.5) < 1e-9
    assert first.ascent_m is not None and first.ascent_m > 0
    assert not splits[1].partial  # ends exactly on the 50 m boundary


def test_distance_splits_absent_stream_is_empty() -> None:
    assert metrics.distance_splits(_session("running", heart_rate=[100, 101])) == []
    assert metrics.distance_splits(_session("running")) == []


def test_session_pace_prefers_moving_denominator() -> None:
    s = _session("running")
    s.derived = Totals(
        elapsed_time_s=3800.0, timer_time_s=3650.0, moving_time_s=3600.0, distance_m=12000.0
    )
    got = metrics.session_pace_s(s, "per_km")
    assert got is not None
    pace, basis = got
    assert basis == "moving" and abs(pace - 300.0) < 1e-9
    s.derived = Totals(elapsed_time_s=3800.0, distance_m=12000.0)
    got = metrics.session_pace_s(s, "per_km")
    assert got is not None and got[1] == "elapsed"
    assert metrics.session_pace_s(_session("running"), "per_km") is None


# --- zone ladder --------------------------------------------------------


def _zone_msgs() -> list[Message]:
    out = []
    for i, hi in enumerate((115, 135, 155, 172, 188)):
        out.append(
            Message(
                global_num=8,
                name="hr_zone",
                local_id=0,
                byte_offset=0,
                fields={"message_index": FieldValue(i), "high_bpm": FieldValue(hi)},
            )
        )
    return out


def test_zone_ladder_settings_beat_file() -> None:
    msgs = _zone_msgs()
    bounds, basis = metrics.hr_zone_bounds(None, msgs)
    assert bounds == (115.0, 135.0, 155.0, 172.0, 188.0) and basis == "file:hr_zone"
    settings = metrics.AthleteSettings(hr_zone_bounds=(120.0, 140.0, 160.0, 175.0, 190.0))
    bounds, basis = metrics.hr_zone_bounds(settings, msgs)
    assert basis == "settings" and bounds is not None and bounds[0] == 120.0
    assert metrics.hr_zone_bounds(None, []) == (None, None)
    assert metrics.power_zone_bounds(None, msgs) == (None, None)  # wrong message name
