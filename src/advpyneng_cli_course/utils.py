import subprocess
from platform import system as system_name
import re
import os
from collections import defaultdict
import tempfile
import pathlib
import stat
import shutil
from datetime import datetime, timedelta

import click
import github
from rich import print as rprint
from rich.padding import Padding

from advpyneng_cli_course.exceptions import AdvPynengError
from advpyneng_cli_course import (
    ANSWERS_URL,
    TASKS_URL,
    TASK_DIRS,
    STUDENT_REPO_TEMPLATE,
)


def red(msg):
    return click.style(msg, fg="red")


def green(msg):
    return click.style(msg, fg="green")


def remove_readonly(func, path, _):
    """
    Вспомогательная функция для Windows, которая позволяет удалять
    read only файлы из каталога .git
    """
    os.chmod(path, stat.S_IWRITE)
    func(path)


def call_command(command, verbose=True, return_stdout=False, return_stderr=False):
    """
    Функция вызывает указанную command через subprocess
    и выводит stdout и stderr, если флаг verbose=True.
    """
    result = subprocess.run(
        command,
        shell=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    std = result.stdout
    stderr = result.stderr
    if return_stdout:
        return std
    if return_stderr:
        return result.returncode, stderr
    if verbose:
        print("#" * 20, command)
        if std:
            print(std)
        if stderr:
            print(stderr)
    return result.returncode


def working_dir_clean():
    git_status = call_command("git status --porcelain", return_stdout=True)
    if git_status:
        return False
    else:
        return True


def show_git_diff_short():
    git_diff = call_command("git diff --stat")
    git_status = call_command("git status")


def git_push(branch):
    """
    Функция вызывает git push для Windows
    """
    command = f"git push origin {branch}"
    print("#" * 20, command)
    result = subprocess.run(command, shell=True)


def save_changes_to_github(
    message="Все изменения сохранены", git_add_all=True, branch="main"
):
    status = call_command("git status -s", return_stdout=True)
    if not status:
        return
    if git_add_all:
        call_command("git add .")
    call_command(f'git commit -m "{message}"')
    windows = True if system_name().lower() == "windows" else False

    if windows:
        git_push(branch)
    else:
        call_command(f"git push origin {branch}")


def get_repo(search_pattern=STUDENT_REPO_TEMPLATE):
    git_remote = call_command("git remote -v", return_stdout=True)
    repo_match = re.search(search_pattern, git_remote)
    if repo_match:
        repo = repo_match.group()
        return repo
    else:
        raise AdvPynengError(
            red(
                f"Не найден репозиторий {STUDENT_REPO_TEMPLATE}. "
                f"apyneng надо вызывать в репозитории подготовленном для курса."
            )
        )


def test_run_for_github_token():
    """
    Функция добавляет тестовое сообщение к последнему за 2 недели коммиту
    """
    message = "Проверка работы токена прошла успешно"
    repo = get_repo()
    last = post_comment_to_last_commit(message, repo)
    commit_number = re.search(r'"(\w+)"', str(last)).group(1)
    print(
        green(
            f"Комментарий можно посмотреть по ссылке "
            f"https://github.com/pyneng/{repo}/commit/{commit_number}"
        )
    )


def post_comment_to_last_commit(msg, repo, delta_days=60, ignore_ssl_cert=False):
    """
    Написать комментарий о сдаче заданий в последнем коммите.
    Комментарий пишется через Github API.

    Для работы функции должен быть настроен git.
    Функция пытается определить имя пользователя git из вывода git config --list,
    Если это не получается, запрашивает имя пользователя.

    Пароль берется из переменной окружения GITHUB_PASS или запрашивается.
    """
    token = os.environ.get("GITHUB_TOKEN")
    since = datetime.now() - timedelta(days=delta_days)
    repo_name = f"pyneng/{repo}"
    verify_ssl_cert = False if ignore_ssl_cert else True
    try:
        g = github.Github(token, verify=verify_ssl_cert)
        repo_obj = g.get_repo(repo_name)
    except github.GithubException:
        raise AdvPynengError(
            red("Аутентификация по токену не прошла. Задание не сдано на проверку")
        )
    else:
        commits = repo_obj.get_commits(since=since)

        try:
            last = commits[0]
        except IndexError:
            print(f"За указанный период времени {delta_days} дней не найдено коммитов")
        else:
            last.create_comment(msg)
            return last


def send_tasks_to_check(
    passed_tasks, git_add_all=False, ignore_ssl_cert=False, branch="main"
):
    """
    Функция отбирает все задания, которые прошли
    тесты при вызове apyneng, делает git add для файлов заданий,
    git commit с сообщением какие задания сделаны
    и git push для добавления изменений на Github.
    После этого к этому коммиту добавляется сообщение о том,
    что задания сдаются на проверку с помощью функции post_comment_to_last_commit.
    """
    ok_tasks = [
        re.sub(r".*(task_\d+_\w+.py)", r"\1", filename) for filename in passed_tasks
    ]
    tasks_num_only = sorted(
        [task.replace("task_", "").replace(".py", "") for task in ok_tasks]
    )
    message = f"Сделаны задания {' '.join(tasks_num_only)}"

    for task in ok_tasks:
        call_command(f"git add {task}")
        # добавление шаблонов для заданий jinja, textfsm
        if "20" in task or "21" in task:
            call_command("git add templates")
        elif "25" in task:
            call_command("git add .")
    save_changes_to_github(message, git_add_all=git_add_all, branch=branch)

    repo = get_repo()
    last = post_comment_to_last_commit(message, repo, ignore_ssl_cert=ignore_ssl_cert)
    commit_number = re.search(r'"(\w+)"', str(last)).group(1)
    print(
        green(
            f"Задание успешно сдано на проверку. Комментарий о сдаче задания "
            f"можно посмотреть по ссылке https://github.com/pyneng/{repo}/commit/{commit_number}"
        )
    )
    hint = (
        "Все задания раздела можно сдать командой:\n"
        "[green on black]apyneng -c[/]\n\n"
        "Не забудьте посмотреть комментарии после проверки.\n"
    )
    rprint(Padding(hint, (1, 0, 1, 4)))


def current_chapter_id():
    """
    Функция возвращает номер текущего раздела, где вызывается apyneng.
    """
    current_chapter_name = current_dir_name()
    current_chapter = int(current_chapter_name.split("_")[0])
    return current_chapter


def current_dir_name():
    pth = str(pathlib.Path().absolute())
    current_chapter_name = os.path.split(pth)[-1]
    return current_chapter_name


def parse_json_report(report):
    """
    Отбирает нужные части из отчета запуска pytest в формате JSON.
    Возвращает список тестов, которые прошли.
    """
    if report and report["summary"]["total"] != 0:
        all_tests = defaultdict(list)
        summary = report["summary"]

        test_names = [test["nodeid"] for test in report["collectors"][0]["result"]]
        for test in report["tests"]:
            name = test["nodeid"].split("::")[0]
            all_tests[name].append(test["outcome"] == "passed")
        all_passed_tasks = [name for name, outcome in all_tests.items() if all(outcome)]
        return all_passed_tasks
    else:
        return []


def git_clone_repo(repo_url, dst_dir):
    returncode, stderr = call_command(
        f"git clone {repo_url} {dst_dir}",
        verbose=False,
        return_stderr=True,
    )
    if returncode != 0:
        if "could not resolve host" in stderr.lower():
            raise AdvPynengError(
                red(
                    "Не получилось клонировать репозиторий. Возможно нет доступа в интернет?"
                )
            )
        else:
            raise AdvPynengError(red(f"Не получилось скопировать файлы. {stderr}"))


def copy_answers(passed_tasks):
    """
    Функция клонирует репозиторий с ответами и копирует ответы для заданий,
    которые прошли тесты.
    """
    pth = str(pathlib.Path().absolute())
    current_chapter_name = os.path.split(pth)[-1]
    current_chapter_number = int(current_chapter_name.split("_")[0])

    homedir = pathlib.Path.home()
    os.chdir(homedir)
    if os.path.exists("advpyneng-answers"):
        shutil.rmtree("advpyneng-answers", onerror=remove_readonly)
    git_clone_repo(ANSWERS_URL, "advpyneng-answers")
    os.chdir(os.path.join("advpyneng-answers", "answers", current_chapter_name))
    copy_answer_files(passed_tasks, pth)
    print(
        green(
            "\nОтветы на задания, которые прошли тесты "
            "скопированы в файлы answer_task_x.py\n"
        )
    )
    os.chdir(homedir)
    shutil.rmtree("advpyneng-answers", onerror=remove_readonly)
    os.chdir(pth)


def copy_answer_files(passed_tasks, pth):
    """
    Функция копирует ответы для указанных заданий.
    """
    for test_file in passed_tasks:
        task_name = test_file.replace("test_", "")
        task_name = re.search(r"task_\w+\.py", task_name).group()
        answer_name = test_file.replace("test_", "answer_")
        answer_name = re.search(r"answer_task_\w+\.py", answer_name).group()
        pth_answer = os.path.join(pth, answer_name)
        if not os.path.exists(pth_answer):
            shutil.copy2(task_name, pth_answer)


def clone_or_pull_task_repo():
    course_tasks_repo_dir = ".advpyneng-course-tasks"
    source_pth = str(pathlib.Path().absolute())
    homedir = pathlib.Path.home()
    os.chdir(homedir)
    if os.path.exists(course_tasks_repo_dir):
        os.chdir(course_tasks_repo_dir)
        call_command("git pull")
        os.chdir(homedir)
    else:
        git_clone_repo(TASKS_URL, course_tasks_repo_dir)
    os.chdir(source_pth)


def copy_tasks_tests_from_repo(tasks, tests):
    """
    Функция клонирует репозиторий с последней версией заданий и копирует указанные
    задания в текущий каталог.
    """
    source_pth = str(pathlib.Path().absolute())
    current_chapter_name = os.path.split(source_pth)[-1]
    current_chapter_number = int(current_chapter_name.split("_")[0])

    clone_or_pull_task_repo()

    course_tasks_repo_dir = ".advpyneng-course-tasks"
    homedir = pathlib.Path.home()
    os.chdir(
        os.path.join(homedir, course_tasks_repo_dir, "exercises", current_chapter_name)
    )
    copy_task_test_files(source_pth, tasks, tests)
    print(green("\nОбновленные задания и тесты скопированы"))
    os.chdir(source_pth)


def copy_task_test_files(source_pth, tasks=None, tests=None):
    """
    Функция копирует файлы заданий и тестов.
    """
    file_list = []
    if tasks:
        file_list += tasks
    if tests:
        file_list += tests
    for file in file_list:
        shutil.copy2(file, os.path.join(source_pth, file))


def save_working_dir(branch="main"):
    if not working_dir_clean():
        print(
            red(
                "Обновление тестов и заданий перезапишет содержимое несохраненных файлов!".upper()
            )
        )
        user_input = input(
            red(
                "В текущем каталоге есть несохраненные изменения! "
                "Хотите их сохранить? [y/n]: "
            )
        )
        if user_input.strip().lower() not in ("n", "no"):
            save_changes_to_github(
                "Сохранение изменений перед обновлением заданий", branch=branch
            )
            print(
                green(
                    "Все изменения в текущем каталоге сохранены. Начинаем обновление..."
                )
            )


def working_dir_changed_diff(branch="main"):
    print(red("Были обновлены такие файлы:"))
    show_git_diff_short()
    print(
        "\nЭто короткий diff, если вы хотите посмотреть все отличия подробно, "
        "нажмите n и дайте команду git diff.\n"
        "Также при желании можно отменить внесенные изменения git checkout -- file "
        "(или git restore file)."
    )

    user_input = input(red("\nСохранить изменения и добавить на github? [y/n]: "))
    if user_input.strip().lower() not in ("n", "no"):
        save_changes_to_github("Обновление заданий", branch=branch)


def update_tasks_and_tests(tasks_list, tests_list, branch="main"):
    save_working_dir(branch=branch)
    copy_tasks_tests_from_repo(tasks_list, tests_list)
    if working_dir_clean():
        print(green("Задания и тесты уже последней версии"))
        return False
    else:
        working_dir_changed_diff(branch=branch)
        return True


def update_chapters_tasks_and_tests(update_chapters, branch="main"):
    save_working_dir(branch=branch)
    copy_chapters_from_repo(update_chapters)
    if working_dir_clean():
        print(green("Все разделы уже последней версии"))
        return False
    else:
        working_dir_changed_diff(branch=branch)
        return True


def copy_chapters_from_repo(chapters_list):
    """
    Функция клонирует репозиторий с последней версией заданий и копирует указанные
    задания в текущий каталог.
    """
    source_pth = str(pathlib.Path().absolute())
    clone_or_pull_task_repo()

    course_tasks_repo_dir = ".advpyneng-course-tasks"
    homedir = pathlib.Path.home()
    os.chdir(os.path.join(homedir, course_tasks_repo_dir, "exercises"))
    copy_chapters(source_pth, chapters_list)
    print(green("\nОбновленные разделы скопированы"))
    os.chdir(source_pth)


def copy_chapters(source_pth, chapters_list):
    """
    Функция копирует разделы
    """
    for chapter in chapters_list:
        to_path = os.path.join(source_pth, chapter)
        if os.path.exists(to_path):
            shutil.rmtree(to_path)
        shutil.copytree(chapter, to_path)
