"""Markdown + YAML front matter parser (python-frontmatter wrapper).

Provides atomic write and partial YAML update. Field order in the YAML block is
preserved as much as python-frontmatter / PyYAML allow (we pass sort_keys=False).
"""
from __future__ import annotations

import os
from pathlib import Path

import frontmatter
import yaml


def _dump(post: frontmatter.Post) -> str:
    return frontmatter.dumps(
        post,
        Dumper=yaml.SafeDumper,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )


def atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def read(path: Path) -> tuple[dict, str]:
    with path.open("r", encoding="utf-8") as fh:
        post = frontmatter.load(fh)
    return dict(post.metadata), post.content


def write(path: Path, yaml_data: dict, body: str) -> None:
    post = frontmatter.Post(body, **yaml_data)
    # Preserve order of yaml_data keys
    post.metadata = dict(yaml_data)
    atomic_write_text(path, _dump(post))


def update_yaml(path: Path, patch: dict) -> None:
    with path.open("r", encoding="utf-8") as fh:
        post = frontmatter.load(fh)
    merged = dict(post.metadata)
    # Update existing keys in place, append new ones at the end.
    for k, v in patch.items():
        merged[k] = v
    post.metadata = merged
    atomic_write_text(path, _dump(post))
