"""Validated, actually consumed study preferences; no model credentials."""
from .common import ExamError, inside, load_json, write_json

DEFAULTS = {"main_source_id": "lecture-yanming-2026", "daily_minutes": None,
            "review_intervals": [1, 3, 7, 14, 30], "review_minutes": 3,
            "question_minutes": 4, "max_self_test_questions": 5}


def validate(data):
    if not isinstance(data, dict) or set(data) - set(DEFAULTS):
        raise ExamError("invalid_settings", "学习配置包含未知字段")
    result = {**DEFAULTS, **data}
    if not isinstance(result["main_source_id"], str) or not result["main_source_id"].strip():
        raise ExamError("invalid_settings", "main_source_id必须指定主讲义来源ID")
    if result["daily_minutes"] is not None and (type(result["daily_minutes"]) is not int or not 5 <= result["daily_minutes"] <= 480):
        raise ExamError("invalid_settings", "daily_minutes应为空或5—480分钟")
    intervals = result["review_intervals"]
    if not isinstance(intervals, list) or not intervals or any(type(v) is not int or not 1 <= v <= 365 for v in intervals) or intervals != sorted(set(intervals)):
        raise ExamError("invalid_settings", "review_intervals应为递增的不重复正整数列表")
    for key, maximum in (("review_minutes", 30), ("question_minutes", 30), ("max_self_test_questions", 10)):
        if type(result[key]) is not int or not 1 <= result[key] <= maximum:
            raise ExamError("invalid_settings", key + "超出支持范围")
    return result


def get(root):
    defaults = inside(root, "config/study-defaults.json")
    local = inside(root, "userdata/study-settings.json")
    data = load_json(defaults) if defaults.exists() else DEFAULTS
    if local.exists():
        data = {**data, **load_json(local)}
    return validate(data)


def update(root, file, apply=False):
    data = validate({**get(root), **load_json(file)})
    if apply:
        write_json(inside(root, "userdata/study-settings.json"), data)
    return {"settings": data, "applied": apply}
