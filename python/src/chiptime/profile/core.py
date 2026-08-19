"""Hand-authored core FIT profile (ADR-0004).

Functional interface facts (message numbers, field numbers, scales, units)
for the messages chiptime interprets semantically. Verified against
fitdecode's MIT-licensed generated profile by
scripts/check_profile_against_fitdecode.py — run it whenever this file changes.

Anything absent here still decodes: unknown messages/fields keep raw values
(contract #6). The wire base type from the file's definition frame is always
authoritative for decoding width; this profile adds naming and semantics only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SEMICIRCLE_SCALE = 2**31 / 180.0  # semicircles → degrees (taxonomy #27)


@dataclass(frozen=True, slots=True)
class FieldDef:
    num: int
    name: str
    kind: str = "number"  # number | enum:<name> | date_time | local_date_time | string | bytes
    scale: float = 1.0
    offset: float = 0.0
    units: str | None = None


@dataclass(frozen=True, slots=True)
class MessageDef:
    num: int
    name: str
    fields: dict[int, FieldDef] = field(default_factory=dict)


def _msg(num: int, name: str, fields: list[FieldDef]) -> MessageDef:
    return MessageDef(num, name, {f.num: f for f in fields})


TIMESTAMP = FieldDef(253, "timestamp", "date_time", units="datetime")
MESSAGE_INDEX = FieldDef(254, "message_index")

MESSAGES: dict[int, MessageDef] = {
    m.num: m
    for m in [
        _msg(
            0,
            "file_id",
            [
                FieldDef(0, "type", "enum:file"),
                FieldDef(1, "manufacturer", "enum:manufacturer"),
                FieldDef(2, "product"),
                FieldDef(3, "serial_number"),
                FieldDef(4, "time_created", "date_time", units="datetime"),
                FieldDef(5, "number"),
                FieldDef(8, "product_name", "string"),
            ],
        ),
        _msg(
            49,
            "file_creator",
            [
                FieldDef(0, "software_version"),
                FieldDef(1, "hardware_version"),
            ],
        ),
        _msg(
            3,
            "user_profile",
            [
                FieldDef(0, "friendly_name", "string"),
                FieldDef(1, "gender", "enum:gender"),
                FieldDef(2, "age", units="years"),
                FieldDef(3, "height", scale=100.0, units="m"),
                FieldDef(4, "weight", scale=10.0, units="kg"),
            ],
        ),
        _msg(
            12,
            "sport",
            [
                FieldDef(0, "sport", "enum:sport"),
                FieldDef(1, "sub_sport", "enum:sub_sport"),
                FieldDef(3, "name", "string"),
            ],
        ),
        _msg(
            18,
            "session",
            [
                TIMESTAMP,
                MESSAGE_INDEX,
                FieldDef(0, "event", "enum:event"),
                FieldDef(1, "event_type", "enum:event_type"),
                FieldDef(2, "start_time", "date_time", units="datetime"),
                FieldDef(3, "start_position_lat", scale=SEMICIRCLE_SCALE, units="deg"),
                FieldDef(4, "start_position_long", scale=SEMICIRCLE_SCALE, units="deg"),
                FieldDef(5, "sport", "enum:sport"),
                FieldDef(6, "sub_sport", "enum:sub_sport"),
                FieldDef(7, "total_elapsed_time", scale=1000.0, units="s"),
                FieldDef(8, "total_timer_time", scale=1000.0, units="s"),
                FieldDef(9, "total_distance", scale=100.0, units="m"),
                FieldDef(10, "total_cycles", units="cycles"),
                FieldDef(11, "total_calories", units="kcal"),
                FieldDef(13, "total_fat_calories", units="kcal"),
                FieldDef(14, "avg_speed", scale=1000.0, units="m/s"),
                FieldDef(15, "max_speed", scale=1000.0, units="m/s"),
                FieldDef(16, "avg_heart_rate", units="bpm"),
                FieldDef(17, "max_heart_rate", units="bpm"),
                FieldDef(18, "avg_cadence", units="rpm"),
                FieldDef(19, "max_cadence", units="rpm"),
                FieldDef(20, "avg_power", units="watts"),
                FieldDef(21, "max_power", units="watts"),
                FieldDef(22, "total_ascent", units="m"),
                FieldDef(23, "total_descent", units="m"),
                FieldDef(24, "total_training_effect", scale=10.0),
                FieldDef(25, "first_lap_index"),
                FieldDef(26, "num_laps"),
                FieldDef(44, "pool_length", scale=100.0, units="m"),
                FieldDef(124, "enhanced_avg_speed", scale=1000.0, units="m/s"),
                FieldDef(125, "enhanced_max_speed", scale=1000.0, units="m/s"),
            ],
        ),
        _msg(
            19,
            "lap",
            [
                TIMESTAMP,
                MESSAGE_INDEX,
                FieldDef(0, "event", "enum:event"),
                FieldDef(1, "event_type", "enum:event_type"),
                FieldDef(2, "start_time", "date_time", units="datetime"),
                FieldDef(3, "start_position_lat", scale=SEMICIRCLE_SCALE, units="deg"),
                FieldDef(4, "start_position_long", scale=SEMICIRCLE_SCALE, units="deg"),
                FieldDef(5, "end_position_lat", scale=SEMICIRCLE_SCALE, units="deg"),
                FieldDef(6, "end_position_long", scale=SEMICIRCLE_SCALE, units="deg"),
                FieldDef(7, "total_elapsed_time", scale=1000.0, units="s"),
                FieldDef(8, "total_timer_time", scale=1000.0, units="s"),
                FieldDef(9, "total_distance", scale=100.0, units="m"),
                FieldDef(10, "total_cycles", units="cycles"),
                FieldDef(11, "total_calories", units="kcal"),
                FieldDef(12, "total_fat_calories", units="kcal"),
                FieldDef(13, "avg_speed", scale=1000.0, units="m/s"),
                FieldDef(14, "max_speed", scale=1000.0, units="m/s"),
                FieldDef(15, "avg_heart_rate", units="bpm"),
                FieldDef(16, "max_heart_rate", units="bpm"),
                FieldDef(17, "avg_cadence", units="rpm"),
                FieldDef(18, "max_cadence", units="rpm"),
                FieldDef(19, "avg_power", units="watts"),
                FieldDef(20, "max_power", units="watts"),
                FieldDef(21, "total_ascent", units="m"),
                FieldDef(22, "total_descent", units="m"),
                FieldDef(25, "sport", "enum:sport"),
            ],
        ),
        _msg(
            20,
            "record",
            [
                TIMESTAMP,
                FieldDef(0, "position_lat", scale=SEMICIRCLE_SCALE, units="deg"),
                FieldDef(1, "position_long", scale=SEMICIRCLE_SCALE, units="deg"),
                FieldDef(2, "altitude", scale=5.0, offset=500.0, units="m"),
                FieldDef(3, "heart_rate", units="bpm"),
                FieldDef(4, "cadence", units="rpm"),
                FieldDef(5, "distance", scale=100.0, units="m"),
                FieldDef(6, "speed", scale=1000.0, units="m/s"),
                FieldDef(7, "power", units="watts"),
                FieldDef(8, "compressed_speed_distance", "bytes"),
                FieldDef(9, "grade", scale=100.0, units="%"),
                FieldDef(13, "temperature", units="C"),
                FieldDef(29, "accumulated_power", units="watts"),
                FieldDef(30, "left_right_balance"),
                FieldDef(39, "vertical_oscillation", scale=10.0, units="mm"),
                FieldDef(40, "stance_time_percent", scale=100.0, units="percent"),
                FieldDef(41, "stance_time", scale=10.0, units="ms"),
                FieldDef(42, "activity_type", "enum:activity_type"),
                FieldDef(53, "fractional_cadence", scale=128.0, units="rpm"),
                FieldDef(73, "enhanced_speed", scale=1000.0, units="m/s"),
                FieldDef(78, "enhanced_altitude", scale=5.0, offset=500.0, units="m"),
                FieldDef(83, "vertical_ratio", scale=100.0, units="percent"),
                FieldDef(84, "stance_time_balance", scale=100.0, units="percent"),
                FieldDef(85, "step_length", scale=10.0, units="mm"),
            ],
        ),
        _msg(
            21,
            "event",
            [
                TIMESTAMP,
                FieldDef(0, "event", "enum:event"),
                FieldDef(1, "event_type", "enum:event_type"),
                FieldDef(2, "data16"),
                FieldDef(3, "data"),
                FieldDef(4, "event_group"),
            ],
        ),
        _msg(
            23,
            "device_info",
            [
                TIMESTAMP,
                FieldDef(0, "device_index"),
                FieldDef(1, "device_type"),
                FieldDef(2, "manufacturer", "enum:manufacturer"),
                FieldDef(3, "serial_number"),
                FieldDef(4, "product"),
                FieldDef(5, "software_version", scale=100.0),
                FieldDef(6, "hardware_version"),
                FieldDef(10, "battery_voltage", scale=256.0, units="V"),
                FieldDef(11, "battery_status"),
                FieldDef(27, "product_name", "string"),
            ],
        ),
        _msg(
            26,
            "workout",
            [
                FieldDef(4, "sport", "enum:sport"),
                FieldDef(6, "num_valid_steps"),
                FieldDef(8, "wkt_name", "string"),
            ],
        ),
        _msg(
            31,
            "course",
            [
                FieldDef(4, "sport", "enum:sport"),
                FieldDef(5, "name", "string"),
            ],
        ),
        _msg(
            34,
            "activity",
            [
                TIMESTAMP,
                FieldDef(0, "total_timer_time", scale=1000.0, units="s"),
                FieldDef(1, "num_sessions"),
                FieldDef(2, "type", "enum:activity"),
                FieldDef(3, "event", "enum:event"),
                FieldDef(4, "event_type", "enum:event_type"),
                FieldDef(5, "local_timestamp", "local_date_time", units="datetime(local)"),
                FieldDef(6, "event_group"),
            ],
        ),
        _msg(
            78,
            "hrv",
            [
                FieldDef(0, "time", scale=1000.0, units="s"),
            ],
        ),
        _msg(
            101,
            "length",
            [
                TIMESTAMP,
                MESSAGE_INDEX,
                FieldDef(0, "event", "enum:event"),
                FieldDef(1, "event_type", "enum:event_type"),
                FieldDef(2, "start_time", "date_time", units="datetime"),
                FieldDef(3, "total_elapsed_time", scale=1000.0, units="s"),
                FieldDef(4, "total_timer_time", scale=1000.0, units="s"),
                FieldDef(5, "total_strokes", units="strokes"),
                FieldDef(6, "avg_speed", scale=1000.0, units="m/s"),
                FieldDef(7, "swim_stroke", "enum:swim_stroke"),
                FieldDef(9, "avg_swimming_cadence", units="strokes/min"),
                FieldDef(10, "event_group"),
                FieldDef(11, "total_calories", units="kcal"),
                FieldDef(12, "length_type", "enum:length_type"),
            ],
        ),
        _msg(
            206,
            "field_description",
            [
                FieldDef(0, "developer_data_index"),
                FieldDef(1, "field_definition_number"),
                FieldDef(2, "fit_base_type_id"),
                FieldDef(3, "field_name", "string"),
                FieldDef(6, "scale"),
                FieldDef(7, "offset"),
                FieldDef(8, "units", "string"),
                FieldDef(13, "fit_base_unit_id"),
                FieldDef(14, "native_mesg_num"),
                FieldDef(15, "native_field_num"),
            ],
        ),
        _msg(
            207,
            "developer_data_id",
            [
                FieldDef(0, "developer_id", "bytes"),
                FieldDef(1, "application_id", "bytes"),
                FieldDef(2, "manufacturer_id", "enum:manufacturer"),
                FieldDef(3, "developer_data_index"),
                FieldDef(4, "application_version"),
            ],
        ),
    ]
}

ENUMS: dict[str, dict[int, str]] = {
    "file": {
        1: "device",
        2: "settings",
        3: "sport",
        4: "activity",
        5: "workout",
        6: "course",
        7: "schedules",
        9: "weight",
        10: "totals",
        11: "goals",
        14: "blood_pressure",
        15: "monitoring_a",
        20: "activity_summary",
        28: "monitoring_daily",
        32: "monitoring_b",
        34: "segment",
        35: "segment_list",
    },
    "manufacturer": {
        1: "garmin",
        23: "suunto",
        32: "wahoo_fitness",
        76: "moxy",
        89: "tacx",
        95: "stryd",
        123: "polar_electro",
        255: "development",
        260: "zwift",
        267: "bryton",
        294: "coros",
        303: "greenteg",
    },
    "sport": {
        0: "generic",
        1: "running",
        2: "cycling",
        3: "transition",
        4: "fitness_equipment",
        5: "swimming",
        6: "basketball",
        7: "soccer",
        8: "tennis",
        9: "american_football",
        10: "training",
        11: "walking",
        12: "cross_country_skiing",
        13: "alpine_skiing",
        14: "snowboarding",
        15: "rowing",
        16: "mountaineering",
        17: "hiking",
        18: "multisport",
        19: "paddling",
    },
    "sub_sport": {
        0: "generic",
        1: "treadmill",
        2: "street",
        3: "trail",
        4: "track",
        5: "spin",
        6: "indoor_cycling",
        7: "road",
        8: "mountain",
        9: "downhill",
        10: "recumbent",
        11: "cyclocross",
        12: "hand_cycling",
        13: "track_cycling",
        14: "indoor_rowing",
        15: "elliptical",
        16: "stair_climbing",
        17: "lap_swimming",
        18: "open_water",
        58: "virtual_activity",
    },
    "event": {
        0: "timer",
        3: "workout",
        4: "workout_step",
        5: "power_down",
        6: "power_up",
        7: "off_course",
        8: "session",
        9: "lap",
        10: "course_point",
        11: "battery",
        12: "virtual_partner_pace",
        13: "hr_high_alert",
        14: "hr_low_alert",
        15: "speed_high_alert",
        16: "speed_low_alert",
        17: "cad_high_alert",
        18: "cad_low_alert",
        19: "power_high_alert",
        20: "power_low_alert",
        21: "recovery_hr",
        22: "battery_low",
        23: "time_duration_alert",
        24: "distance_duration_alert",
        25: "calorie_duration_alert",
        26: "activity",
        27: "fitness_equipment",
        28: "length",
        32: "user_marker",
        33: "sport_point",
        36: "calibration",
        42: "front_gear_change",
        43: "rear_gear_change",
        44: "rider_position_change",
        45: "elev_high_alert",
        46: "elev_low_alert",
        47: "comm_timeout",
    },
    "event_type": {
        0: "start",
        1: "stop",
        2: "consecutive_depreciated",
        3: "marker",
        4: "stop_all",
        5: "begin_depreciated",
        6: "end_depreciated",
        7: "end_all_depreciated",
        8: "stop_disable",
        9: "stop_disable_all",
    },
    "activity": {0: "manual", 1: "auto_multi_sport"},
    "activity_type": {
        0: "generic",
        1: "running",
        2: "cycling",
        3: "transition",
        4: "fitness_equipment",
        5: "swimming",
        6: "walking",
        8: "sedentary",
    },
    "swim_stroke": {
        0: "freestyle",
        1: "backstroke",
        2: "breaststroke",
        3: "butterfly",
        4: "drill",
        5: "mixed",
        6: "im",
    },
    "length_type": {0: "idle", 1: "active"},
    "gender": {0: "female", 1: "male"},
}
