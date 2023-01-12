import sys
import re
import os
import json
from glob import glob

import click
import pytest
from rich.console import Console
from rich.markdown import Markdown
from pytest_jsonreport.plugin import JSONReport

from advpyneng_cli_course import (
    DEFAULT_BRANCH,
    TASK_DIRS,
    DB_TASK_DIRS,
    TASK_NUMBER_DIR_MAP,
)
from advpyneng_cli_course.exceptions import AdvPynengError
from advpyneng_cli_course.apyneng_docs import DOCS
from advpyneng_cli_course.utils import (
    red,
    green,
    save_changes_to_github,
    test_run_for_github_token,
    send_tasks_to_check,
    current_chapter_id,
    current_dir_name,
    parse_json_report,
    copy_answers,
    update_tasks_and_tests,
    update_chapters_tasks_and_tests,
)


def exception_handler(exception_type, exception, traceback):
    """
    sys.excepthook для отключения traceback по умолчанию
    """
    print(f"\n{exception_type.__name__}: {exception}\n")


def check_current_dir_name(dir_list, message):
    current_chapter = current_dir_name()
    if current_chapter not in dir_list:
        task_dirs_line = "\n    ".join(
            [d for d in dir_list if not d.startswith("task")]
        )
        print(red(f"\n{message}:" f"\n    {task_dirs_line}"))
        raise click.Abort()


def _get_tasks_tests_from_cli(self, value):
    regex = (
        r"(?P<all>all)|"
        r"(?P<number_star>\d\*)|"
        r"(?P<letters_range>\d[a-i]-[a-i])|"
        r"(?P<numbers_range>\d-\d)|"
        r"(?P<single_task>\d[a-i]?)"
    )
    tasks_list = re.split(r"[ ,]+", value)
    current_chapter = current_chapter_id()
    test_files = []
    task_files = []
    for task in tasks_list:
        match = re.fullmatch(regex, task)
        if match:
            if task == "all":
                test_files = sorted(glob(f"test_task_{current_chapter}_*.py"))
                task_files = sorted(glob(f"task_{current_chapter}_*.py"))
                break
            else:
                if match.group("letters_range"):
                    task = f"{task[0]}[{task[1:]}]"  # convert 1a-c to 1[a-c]
                elif match.group("numbers_range"):
                    task = f"[{task}]"  # convert 1-3 to [1-3]

                test_files += glob(f"test_task_{current_chapter}_{task}.py")
                task_files += glob(f"task_{current_chapter}_{task}.py")
        else:
            self.fail(
                red(
                    f"Данный формат не поддерживается {task}. "
                    "Допустимые форматы в apyneng --help"
                )
            )
    tasks_with_tests = set([test.replace("test_", "") for test in test_files])
    tasks_without_tests = set(task_files) - tasks_with_tests
    return sorted(test_files), sorted(tasks_without_tests), sorted(task_files)


class CustomTasksType(click.ParamType):
    """
    Класс создает новый тип для click и преобразует
    допустимые варианты строк заданий в отдельные файлы тестов.

    Кроме того проверяет есть ли такой файл в текущем каталоге
    и оставляет только те, что есть.
    """

    name = "CustomTasksType"

    def convert(self, value, param, ctx):
        if isinstance(value, tuple):
            return value
        elif value == "all" and current_dir_name() == "exercises":
            return value
        elif current_dir_name() not in TASK_DIRS:
            return value

        return _get_tasks_tests_from_cli(self, value)


class CustomChapterType(click.ParamType):
    name = "Chapters"

    def convert(self, value, param, ctx):
        if isinstance(value, tuple):
            return value
        regex = r"(?P<numbers_range>\d+-\d+)|" r"(?P<number>\d+)"
        TASK_NUMBER_DIR_MAP
        chapter_dir_list = []
        chapter_list = re.split(r"[ ,]+", value)
        for chapter in chapter_list:
            match = re.fullmatch(regex, chapter)
            if match:
                if match.group("number"):
                    chapter = int(match.group("number"))
                    chapter_dir = TASK_NUMBER_DIR_MAP.get(chapter)
                    if chapter_dir:
                        chapter_dir_list.append(chapter_dir)
                elif match.group("numbers_range"):
                    start, stop = match.group("numbers_range").split("-")
                    for chapter_id in range(int(start), int(stop) + 1):
                        chapter_dir = TASK_NUMBER_DIR_MAP.get(chapter_id)
                        if chapter_dir:
                            chapter_dir_list.append(chapter_dir)
            else:
                self.fail(
                    red(
                        f"Данный формат не поддерживается {chapter}. "
                        "Допустимые форматы в apyneng --help"
                    )
                )
        return sorted(chapter_dir_list)


def print_docs_with_pager(width=90):
    console = Console(width=width)
    md = Markdown(DOCS)
    with console.pager():
        console.print(md)


@click.command(
    context_settings=dict(
        ignore_unknown_options=True, help_option_names=["-h", "--help"]
    )
)
@click.argument("tasks", default="all", type=CustomTasksType())
@click.option(
    "--check",
    "-c",
    is_flag=True,
    help=(
        "Сдать задания на проверку. "
        "При добавлении этого флага, "
        "не выводится traceback для тестов."
    ),
)
@click.option("--docs", is_flag=True, help="Показать документацию apyneng")
@click.option("--test-token", is_flag=True, help="Проверить работу токена")
@click.option(
    "--save-all",
    "save_all_to_github",
    is_flag=True,
    help="Сохранить на GitHub все измененные файлы в текущем каталоге",
)
@click.option(
    "--update", "update_tasks_tests", is_flag=True, help="Обновить задания и тесты"
)
@click.option(
    "--test-only", "update_tests_only", is_flag=True, help="Обновить только тесты"
)
@click.option(
    "--update-chapters",
    type=CustomChapterType(),
    help="Обновить все задания и тесты в указанных разделах",
)
@click.option(
    "--disable-verbose", "-d", is_flag=True, help="Отключить подробный вывод pytest"
)
@click.option("--debug", is_flag=True, help="Показывать traceback исключений")
@click.option("--default-branch", "-b", default="main")
@click.option(
    "--all",
    "git_add_all_to_github",
    is_flag=True,
    help="Добавить git add .",
)
@click.option("--ignore-ssl-cert", default=False)
@click.version_option(version="1.1.0")
def cli(
    tasks,
    disable_verbose,
    check,
    debug,
    default_branch,
    test_token,
    git_add_all_to_github,
    ignore_ssl_cert,
    update_tasks_tests,
    update_tests_only,
    save_all_to_github,
    update_chapters,
    docs,
):
    """
    Запустить тесты для заданий TASKS. По умолчанию запустятся все тесты.

    \b
    Эти флаги не запускают тестирование заданий
     apyneng --docs                 Показать документацию apyneng
     apyneng --test-token           Проверить работу токена
     apyneng --save-all             Сохранить на GitHub все измененные файлы в текущем каталоге
     apyneng --update               Обновить все задания и тесты в текущем каталоге
     apyneng --update --test-only   Обновить только тесты в текущем каталоге
     apyneng 1,2 --update           Обновить задания 1 и 2 и соответствующие тесты в текущем каталоге
     apyneng --update-chapters 4-5  Обновить разделы 4 и 5 (каталоги будут удалены и скопированы обновленные версии)

    \b
    Запуск тестирования заданий, просмотр ответов, сдача на проверку
    \b
        apyneng              запустить все тесты для текущего раздела
        apyneng 1,2a,5       запустить тесты для заданий 1, 2a и 5
        apyneng 1,2*         запустить тесты для заданий 1, все задания 2 с буквами и без
        apyneng 1,3-5        запустить тесты для заданий 1, 3, 4, 5
        apyneng 1-5 -c       запустить тесты и сдать на проверку задания,
                             которые прошли тесты.
        apyneng 1-5 -c --all запустить тесты и сдать на проверку задания,
                             которые прошли тесты, но при этом загрузить на github все изменения
                             в текущем каталоге

    \b
    Подробнее в документации: apyneng --docs
    """
    global DEFAULT_BRANCH
    if default_branch != "main":
        DEFAULT_BRANCH = default_branch
    token_error = red(
        "Для сдачи заданий на проверку надо сгенерировать токен github. "
        "Подробнее в инструкции: https://advpyneng.natenka.io/docs/apyneng-prepare/"
    )
    if docs:
        print_docs_with_pager()
        raise click.Abort()

    if test_token:
        test_run_for_github_token()
        print(green("Проверка токена прошла успешно"))
        raise click.Abort()

    if save_all_to_github:
        save_changes_to_github(branch=DEFAULT_BRANCH)
        print(green("Все изменения в текущем каталоге сохранены на GitHub"))
        raise click.Abort()

    if update_chapters:
        check_current_dir_name(
            ["exercises"], "Обновление разделов надо выполнять из каталога"
        )
        update_chapters_tasks_and_tests(update_chapters, branch=DEFAULT_BRANCH)
        raise click.Abort()

    # дальнейшее есть смысл выполнять только если мы находимся в каталоге
    # конкретного раздела с заданиями
    check_current_dir_name(
        TASK_DIRS + DB_TASK_DIRS, "Проверку заданий можно выполнять только из каталогов"
    )

    # после обработки CustomTasksType, получаем три списка файлов
    test_files, tasks_without_tests, task_files = tasks

    if update_tasks_tests:
        if update_tests_only:
            tasks_files = None
            msg = green("Тесты успешно обновлены")
        else:
            msg = green("Задания и тесты успешно обновлены")

        upd = update_tasks_and_tests(task_files, test_files, branch=DEFAULT_BRANCH)
        if upd:
            print(msg)
        raise click.Abort()

    if not debug:
        sys.excepthook = exception_handler

    json_plugin = JSONReport()
    pytest_args_common = ["--json-report-file=none", "--disable-warnings"]

    if disable_verbose:
        pytest_args = [*pytest_args_common, "--tb=short"]
    else:
        pytest_args = [*pytest_args_common, "-vv", "--diff-width=120"]

    # если добавлен флаг -c нет смысла выводить traceback,
    # так как скорее всего задания уже проверены предыдущими запусками.
    if check:
        pytest_args = [*pytest_args_common, "--tb=no"]

    # запуск pytest
    pytest.main(test_files + pytest_args, plugins=[json_plugin])

    # получить результаты pytest в формате JSON
    # passed_tasks это задания у которых есть тесты и тесты прошли
    passed_tasks = parse_json_report(json_plugin.report)

    if passed_tasks or tasks_without_tests:
        # сдать задания на проверку через github API
        if check:
            token = os.environ.get("GITHUB_TOKEN")
            if not token:
                raise AdvPynengError(token_error)
            send_tasks_to_check(
                passed_tasks + tasks_without_tests,
                git_add_all=git_add_all_to_github,
                ignore_ssl_cert=ignore_ssl_cert,
                branch=DEFAULT_BRANCH
            )

    # если добавлен флаг --all, надо сохранить все изменения на github
    if git_add_all_to_github:
        save_changes_to_github(branch=DEFAULT_BRANCH)


if __name__ == "__main__":
    cli()
