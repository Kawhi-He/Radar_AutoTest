# Radar_AutoTest

Pytest-based automation runner integrated with Feishu MiaoDa platform.

## 1. Goal

This repository provides a maintainable automation framework with:

- Runner polling and reporting (`automation_runner.py`)
- Case routing (`run_case.py`)
- Pytest lifecycle init/cleanup (`tests/conftest.py`)
- Project-based case organization (`tests/projects/...`)
- Local log generation (`logs/`) and result callback to platform

## 2. Current Demo Scope

- Project demo: `LINKE` (normalized key: `linke`)
- Demo cases:
  - `LKE-001` -> `test_linke_connection_smoke`
  - `LKE-002` -> `test_linke_data_process_smoke`

Mapping file: `case-map.json`

## 3. Directory Structure

```text
Radar_AutoTest/
|- automation_runner.py
|- run_case.py
|- runner-config.json
|- case-map.json
|- requirements.txt
|- logs/
|- tests/
	|- conftest.py
	|- projects/
		|- linke/
			|- test_linke_demo.py
```

## 4. Install Dependencies

```bash
python -m pip install -r requirements.txt
```

## 5. Local Debug Commands

Run one mapped case:

```bash
python run_case.py --project linkeda --case-no LKE-001 --case-name "linke smoke" --base-id 1001
```

Run all LINKE tests (without case number):

```bash
python run_case.py --project linkeda
```

## 6. Start Runner (same as your current usage)

```bash
python automation_runner.py runner-config.json
```

Runner behavior:

- Polls task from platform
- Executes command from per-case script or fallback `command`
- Returns status: `pass` / `fail` / `error`
- Returns stdout/stderr tail as task log

## 7. Suggested Script on MiaoDa Case Page

For each case in platform "Automation" panel, set script like:

```bash
python run_case.py --project linkeda --case-no {case_no} --case-name "{case_name}" --base-id {base_id}
```

If per-case script is empty, runner falls back to `runner-config.json` `command`.

## 8. How to Add New Project (AIMA example)

1. Add test files under `tests/projects/aima/`
2. Add case mappings in `case-map.json` -> `projects.aima`
3. Use project key in script/config:

```bash
python run_case.py --project aima --case-no {case_no}
```

No runner code change is required for adding mapped cases.
