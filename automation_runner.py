#!/usr/bin/env python3
"""雷达测试台 —— 自动化测试执行机（runner）

用途
    本脚本部署在测试电脑上，持续轮询应用服务端领取自动化任务，
    在本地拉取最新测试脚本、执行命令，并把结果回传给服务端。

执行模式（两种，按任务内容自动选择）
    1. 用例已配置 git/脚本（按任务配置拉取执行）
       任务携带非空 gitRepo（以及 gitBranch / script）时进入该模式：
       runner 把该用例的脚本仓库缓存到 repo_cache_dir/<仓库+分支哈希>，
       复用缓存时执行 git fetch + git reset --hard origin/<branch>，
       缓存缺失或 remote 不匹配时删除后重新 git clone；
       随后在**该仓库目录**内执行任务携带的 script（占位符同下）。
       gitCommit 取该仓库目录的 git rev-parse HEAD。
    2. 未配置 per-case（回退本地工作目录模式）
       任务没有 gitRepo 时保持原有行为：
       在本地 workdir 里 git fetch + reset，按配置项 command 执行。

使用步骤
    1. 复制 runner-config.example.json 为 runner-config.json，按实际环境填写：
         base_url    应用对外访问地址（线上域名，不带结尾斜杠），如 https://qa.example.com
         api_key     线上开放接口 API Key（以 Authorization: Bearer 头发送）；如网关未开启鉴权可留空字符串
         projects    项目标识列表，如 ["fall", "linkeda"]；按顺序轮流轮询，任务串行执行
                    （单项目仍可只写 project 字符串，二者取其一；项目名限
                    fall / linkeda / am / vital / door，写错会本地直接报错）
                    注意 project 只能写单个字符串，多项目请用 projects 数组
         name        执行机名称，如 雷达测试机-01；服务端按此名称派发定向任务
         git_repo    测试脚本仓库（仅作说明保留，仓库地址由 workdir 的 remote 决定）
         git_branch  回退模式下拉取的分支；用例未填 gitBranch 时也用此值兜底
         workdir     回退模式的本地工作目录，必须已经是该仓库的 git 工作副本
         command     回退模式的执行命令模板，可用占位符 {project} {case_no} {case_name} {base_id}
                     用例已配置 git 但 script 为空时，也用它在本用例仓库目录里执行
         repo_cache_dir  按用例拉取脚本时的仓库缓存根目录，默认 ./repo-cache（不存在自动创建）
         poll_interval 轮询间隔秒数，默认 3
    2. API Key 来源：妙搭应用后台 → 开放能力 / OpenAPI → API Key 管理，创建后复制。
    3. 运行：python3 automation_runner.py runner-config.json
       脚本的 stdout / stderr 会同时打印在本终端，并回传服务端
       （录入页「自动化测试」面板悬停任务行可看完整日志）。
    4. 常驻：
         Linux   nohup python3 automation_runner.py runner-config.json >> runner.log 2>&1 &
         Windows 用「任务计划程序」创建开机启动任务，程序填 python，参数填脚本与配置路径。

判定规则
    命令返回码 0 → pass；非 0 → fail；
    git 拉取（fetch / reset / clone）失败或执行异常、超时 → error。

依赖
    仅使用 Python 3 标准库，无需 pip 安装。
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

MAX_LOG_CHARS = 8000
SUPPORTED_PROJECTS = ("fall", "linkeda", "am", "vital", "door")


def log(message):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print("[%s] %s" % (stamp, message), flush=True)


def load_config(path):
    with open(path, "r", encoding="utf-8") as handle:
        config = json.load(handle)
    required = ["base_url", "name", "workdir", "command"]
    for key in required:
        if not config.get(key):
            raise SystemExit("配置缺少必填项：%s" % key)
    raw_projects = config.get("projects")
    if isinstance(raw_projects, list):
        candidates = [str(item or "").strip() for item in raw_projects]
    else:
        raw_project = config.get("project")
        if isinstance(raw_project, list):
            candidates = [str(item or "").strip() for item in raw_project]
        else:
            candidates = [str(raw_project or raw_projects or "").strip()]
    projects = []
    for name in candidates:
        if name and name not in projects:
            projects.append(name)
    if not projects:
        raise SystemExit("配置缺少必填项：project 或 projects")
    unsupported = [name for name in projects if name not in SUPPORTED_PROJECTS]
    if unsupported:
        raise SystemExit(
            "配置含不支持的项目：%s（可选 %s）"
            % ("、".join(unsupported), " / ".join(SUPPORTED_PROJECTS))
        )
    config["projects"] = projects
    config["base_url"] = config["base_url"].rstrip("/")
    config.setdefault("api_key", "")
    config.setdefault("git_branch", "main")
    config.setdefault("git_repo", "")
    config.setdefault("poll_interval", 3)
    config.setdefault("repo_cache_dir", "./repo-cache")
    try:
        os.makedirs(config["repo_cache_dir"], exist_ok=True)
    except OSError as error:
        raise SystemExit("仓库缓存目录创建失败：%s（%s）" % (config["repo_cache_dir"], error))
    return config


def post_json(config, path, payload):
    url = config["base_url"] + path
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if config.get("api_key"):
        # 妙搭开放接口网关只认 Authorization: Bearer <API Key>，X-Api-Key 会被忽略
        headers["Authorization"] = "Bearer %s" % config["api_key"]
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace").strip()[:500]
        message = "HTTP %s %s" % (error.code, path)
        if detail:
            message += "：%s" % detail
        raise RuntimeError(message)
    return json.loads(raw) if raw else {}


def poll_task(config, project):
    return post_json(
        config,
        "/openapi/automation/poll",
        {"projectKey": project, "runnerName": config["name"]},
    ).get("task")


def report_result(config, run_id, status, text, git_commit):
    try:
        post_json(
            config,
            "/openapi/automation/report",
            {
                "runId": run_id,
                "status": status,
                "log": text[-MAX_LOG_CHARS:],
                "gitCommit": git_commit,
            },
        )
    except (urllib.error.URLError, OSError, ValueError) as error:
        log("结果回传失败：%s" % error)


def run_git(repo_dir, args):
    return subprocess.run(
        ["git", "-C", repo_dir] + args,
        capture_output=True,
        text=True,
        timeout=600,
    )


def sync_repo(config):
    fetch = run_git(config["workdir"], ["fetch", "origin"])
    if fetch.returncode != 0:
        return "git fetch 失败：\n%s\n%s" % (fetch.stdout, fetch.stderr)
    reset = run_git(
        config["workdir"], ["reset", "--hard", "origin/%s" % config["git_branch"]]
    )
    if reset.returncode != 0:
        return "git reset 失败：\n%s\n%s" % (reset.stdout, reset.stderr)
    return None


def head_commit(repo_dir):
    result = run_git(repo_dir, ["rev-parse", "HEAD"])
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def repo_slug(repo, branch):
    """按仓库地址 + 分支生成稳定的缓存目录名（sha1 十六进制前 16 位）。"""
    key = "%s@%s" % (repo, branch)
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def remote_url(repo_dir):
    result = run_git(repo_dir, ["remote", "get-url", "origin"])
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def clone_repo(repo, branch, repo_dir):
    return subprocess.run(
        ["git", "clone", "--branch", branch, repo, repo_dir],
        capture_output=True,
        text=True,
        timeout=1800,
    )


def prepare_case_repo(config, repo, branch):
    """准备 per-case 脚本仓库，返回 (仓库目录, 失败说明)；成功时失败说明为 None。"""
    repo_dir = os.path.join(config["repo_cache_dir"], repo_slug(repo, branch))
    if os.path.isdir(os.path.join(repo_dir, ".git")) and remote_url(repo_dir) == repo:
        fetch = run_git(repo_dir, ["fetch", "origin"])
        if fetch.returncode != 0:
            return repo_dir, "git fetch 失败：\n%s\n%s" % (fetch.stdout, fetch.stderr)
        reset = run_git(repo_dir, ["reset", "--hard", "origin/%s" % branch])
        if reset.returncode != 0:
            return repo_dir, "git reset 失败：\n%s\n%s" % (reset.stdout, reset.stderr)
        return repo_dir, None

    # 缓存不可复用（不存在、不是仓库、或 remote 不是本用例配置的仓库）：删除后重新克隆
    if os.path.isdir(repo_dir):
        log("缓存目录不可复用，删除后重新克隆：%s" % repo_dir)
        shutil.rmtree(repo_dir, ignore_errors=True)
    log("克隆用例脚本仓库：%s（分支 %s）" % (repo, branch))
    clone = clone_repo(repo, branch, repo_dir)
    if clone.returncode != 0:
        return repo_dir, "git clone 失败：\n%s\n%s" % (clone.stdout, clone.stderr)
    return repo_dir, None


def build_command(config, task):
    return config["command"].format(
        project=task.get("projectKey", ""),
        case_no=task.get("caseNo", ""),
        case_name=task.get("caseName", ""),
        base_id=task.get("baseId", ""),
    )


def fill_placeholders(template, task):
    """替换 {project}/{case_no}/{case_name}/{base_id}，缺字段替换为空串。"""
    text = template.replace("{project}", str(task.get("projectKey") or ""))
    text = text.replace("{case_no}", str(task.get("caseNo") or ""))
    text = text.replace("{case_name}", str(task.get("caseName") or ""))
    text = text.replace("{base_id}", str(task.get("baseId") or ""))
    return text


def build_case_command(config, task):
    """per-case 模式命令：优先用任务携带的 script，为空时回退配置里的 command。"""
    script = str(task.get("script") or "").strip() or config["command"]
    return fill_placeholders(script, task)


def execute_task(config, run_id, command, workdir, commit):
    log("执行命令：%s" % command)
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=3600,
        )
        if result.stdout:
            print(result.stdout.rstrip(), flush=True)
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr, flush=True)
        output = "[stdout]\n%s\n[stderr]\n%s" % (result.stdout or "", result.stderr or "")
        status = "pass" if result.returncode == 0 else "fail"
        output = "exit=%s\n%s" % (result.returncode, output)
    except subprocess.TimeoutExpired as error:
        status = "error"
        output = "执行超时：%s" % error
    except OSError as error:
        status = "error"
        output = "执行异常：%s" % error

    log("执行结束，结论 %s" % status)
    report_result(config, run_id, status, output, commit)


def handle_case_task(config, task, run_id, repo):
    """per-case 模式：按任务携带的仓库/分支拉取脚本，并在该仓库目录内执行。"""
    branch = str(task.get("gitBranch") or "").strip() or config["git_branch"]
    log("用例已配置自动化脚本：%s@%s" % (repo, branch))

    repo_dir, git_error = prepare_case_repo(config, repo, branch)
    commit = head_commit(repo_dir) if os.path.isdir(repo_dir) else ""
    if git_error:
        log("脚本拉取失败，回传 error")
        report_result(config, run_id, "error", git_error, commit)
        return

    execute_task(config, run_id, build_case_command(config, task), repo_dir, commit)


def handle_task(config, task, project):
    run_id = task.get("runId", "")
    task["projectKey"] = task.get("projectKey") or project
    log(
        "[%s] 领取任务 %s（%s %s）"
        % (project, run_id, task.get("caseNo", ""), task.get("caseName", ""))
    )

    repo = str(task.get("gitRepo") or "").strip()
    if repo:
        handle_case_task(config, task, run_id, repo)
        return

    git_error = sync_repo(config)
    commit = head_commit(config["workdir"])
    if git_error:
        log("脚本拉取失败，回传 error")
        report_result(config, run_id, "error", git_error, commit)
        return

    execute_task(config, run_id, build_command(config, task), config["workdir"], commit)


def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else "runner-config.json"
    if not os.path.isfile(config_path):
        raise SystemExit("配置文件不存在：%s" % config_path)
    config = load_config(config_path)
    log(
        "执行机 %s 启动，服务端 %s，项目 %s"
        % (config["name"], config["base_url"], "、".join(config["projects"]))
    )

    try:
        while True:
            handled = False
            for project in config["projects"]:
                try:
                    task = poll_task(config, project)
                except (urllib.error.URLError, OSError, RuntimeError, ValueError) as error:
                    log("[%s] 轮询失败：%s" % (project, error))
                    continue
                if not task:
                    continue
                handle_task(config, task, project)
                handled = True
            if not handled:
                time.sleep(float(config["poll_interval"]))
    except KeyboardInterrupt:
        log("已停止")


if __name__ == "__main__":
    main()