#!/usr/bin/env python3
"""Điền giá trị động vào user-data.template một cách an toàn.

Nhận giá trị qua argv (không nhúng trực tiếp vào mã nguồn Python bằng cách
nội suy chuỗi trong bash) để mật khẩu/khoá SSH có ký tự đặc biệt (dấu ngoặc
kép, backslash...) không làm vỡ cú pháp.
"""

from __future__ import annotations

import argparse
import json
import shlex


def yaml_dquote(s: str) -> str:
    """Trả về chuỗi trong dấu nháy kép hợp lệ cho YAML — cú pháp escape của
    JSON string là tập con hợp lệ của YAML double-quoted scalar nên dùng
    json.dumps là đủ an toàn, không cần tự viết escape riêng."""
    return json.dumps(s)


def bash_single_quote(s: str) -> str:
    """Escape 1 chuỗi để nhúng an toàn bên trong cặp nháy đơn '...' của bash
    (dùng cho URL git trong late-commands)."""
    return s.replace("'", "'\\''")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("template")
    p.add_argument("output")
    p.add_argument("--hostname", required=True)
    p.add_argument("--admin-user", required=True)
    p.add_argument("--admin-password-hash", required=True)
    p.add_argument("--ssh-allow-pw", required=True, choices=["true", "false"])
    p.add_argument("--ssh-pubkey", default="")
    p.add_argument("--repo-url", required=True)
    p.add_argument("--http-port", required=True)
    p.add_argument("--library", action="append", default=[])
    args = p.parse_args()

    authorized_keys = f"[{yaml_dquote(args.ssh_pubkey)}]" if args.ssh_pubkey else "[]"
    library_args = "".join(
        f" --library {shlex.quote(lib)}" for lib in args.library if lib
    )

    subs = {
        "__LENN_HOSTNAME__": args.hostname,
        "__LENN_ADMIN_USER__": args.admin_user,
        "__LENN_ADMIN_PASSWORD_HASH__": args.admin_password_hash,
        "__LENN_SSH_ALLOW_PW__": args.ssh_allow_pw,
        "[__LENN_SSH_AUTHORIZED_KEYS__]": authorized_keys,  # thay cả cặp ngoặc mẫu
        "__LENN_CORE_REPO_URL__": bash_single_quote(args.repo_url),
        "__LENN_HTTP_PORT__": args.http_port,
        "__LENN_LIBRARY_ARGS__": library_args,
    }

    text = open(args.template, encoding="utf-8").read()
    for key, value in subs.items():
        text = text.replace(key, value)

    if "__LENN_" in text:
        remaining = sorted(set(part.split("__")[1] for part in text.split("__LENN_")[1:]))
        raise SystemExit(f"LỖI: template còn placeholder chưa thay: {remaining}")

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(text)


if __name__ == "__main__":
    main()
