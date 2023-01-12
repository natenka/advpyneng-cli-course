__version__ = "1.1.0"

ANSWERS_URL = "https://github.com/pyneng/pyneng-course-answers"
# needed for tasks/tests updates
TASKS_URL = "https://github.com/pyneng/advpyneng-course-tasks"
DEFAULT_BRANCH = "main"
STUDENT_REPO_TEMPLATE = r"advpyneng-\d+-\w+-\w+"
TASK_DIRS = [
    "01_pytest_basics",
    "02_type_annotations",
    "04_click",
    "05_logging",
    "07_closure",
    "08_decorators",
    "09_oop_basics",
    "10_oop_special_methods",
    "11_oop_method_decorators",
    "12_oop_inheritance",
    "13_data_classes",
    "14_generators",
    "17_async_libraries",
    "18_using_asyncio",
]
# TASK_DIRS_WITHOUT_TESTS = ["01", "05", "17", "18"]

TASK_NUMBER_DIR_MAP = {
    1: "01_pytest_basics",
    2: "02_type_annotations",
    4: "04_click",
    5: "05_logging",
    7: "07_closure",
    8: "08_decorators",
    9: "09_oop_basics",
    10: "10_oop_special_methods",
    11: "11_oop_method_decorators",
    12: "12_oop_inheritance",
    13: "13_data_classes",
    14: "14_generators",
    17: "17_async_libraries",
    18: "18_using_asyncio",
}

DB_TASK_DIRS = [
]

# from importlib import resources
# import json
#
# Read URL from config file
# _cfg = json.loads(resources.read_text("pyneng", "config.json"))
# ANSWERS_URL = _cfg["answers_url"]
# TASKS_URL = _cfg["tasks_url"]

