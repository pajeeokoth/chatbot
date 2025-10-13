#!/usr/bin/env python3
"""Helpers to persist LUIS app id and endpoint to .env or a local config file.

Usage:
  from scripts.write_luis_config import write_config
  write_config(app_id, endpoint, target='env')

This module creates backups before overwriting existing files.
"""

import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional


def _backup(path: Path):
    if path.exists():
        stamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        bak = path.with_name(path.name + f'.bak.{stamp}')
        shutil.copy2(path, bak)
        return bak
    return None


def write_env(app_id: str, endpoint: str, prediction_key: Optional[str] = None, repo_root: Optional[str] = None):
    repo_root = repo_root or Path(__file__).resolve().parents[1]
    env_path = Path(repo_root) / '.env'
    _backup(env_path)

    lines = []
    if env_path.exists():
        lines = env_path.read_text(encoding='utf-8').splitlines()

    def set_env(lines, key, value):
        key_eq = key + '='
        for i, l in enumerate(lines):
            if l.startswith(key_eq):
                lines[i] = f"{key}={value}"
                return lines
        lines.append(f"{key}={value}")
        return lines

    lines = set_env(lines, 'LUIS_APP_ID', app_id)
    if endpoint:
        lines = set_env(lines, 'LUIS_ENDPOINT', endpoint)
    if prediction_key:
        lines = set_env(lines, 'LUIS_PREDICTION_KEY', prediction_key)

    env_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return str(env_path)


def write_config_local(app_id: str, endpoint: str, prediction_key: Optional[str] = None, repo_root: Optional[str] = None):
    repo_root = Path(repo_root or Path(__file__).resolve().parents[1])
    cfg_dir = repo_root / 'mytravel'
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = cfg_dir / 'config_local.py'
    _backup(cfg_path)

    lines = [
        '# Auto-generated LUIS local overrides. Safe to commit if you wish,\n',
        f"LUIS_APP_ID = '{app_id}'\n",
        f"LUIS_ENDPOINT = '{endpoint}'\n",
    ]
    if prediction_key:
        lines.append(f"LUIS_PREDICTION_KEY = '{prediction_key}'\n")

    cfg_path.write_text(''.join(lines), encoding='utf-8')
    return str(cfg_path)


def write_config(app_id: str, endpoint: str, prediction_key: Optional[str] = None, target: str = 'env'):
    """Write app id and endpoint to target: 'env' or 'config'. Returns path written."""
    repo_root = Path(__file__).resolve().parents[1]
    if target == 'env':
        return write_env(app_id, endpoint, prediction_key=prediction_key, repo_root=repo_root)
    elif target == 'config':
        return write_config_local(app_id, endpoint, prediction_key=prediction_key, repo_root=repo_root)
    else:
        raise ValueError('Unknown target: ' + target)


if __name__ == '__main__':
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument('--app-id', required=True)
    p.add_argument('--endpoint', required=True)
    p.add_argument('--prediction-key', help='optional prediction key to include')
    p.add_argument('--target', choices=['env', 'config'], default='env')
    args = p.parse_args()
    path = write_config(args.app_id, args.endpoint, prediction_key=args.prediction_key, target=args.target)
    print('Wrote:', path)
