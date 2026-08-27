"""Probe WeChat Official Account publishing capability (read-only + self-cleaning).

Usage:
    python -X utf8 scripts/probe_wechat.py [--appid X --secret Y]

Reads appid/secret from config.yaml wechat section if not passed.
Steps:
  1. get_access_token          -> validates credentials + IP whitelist (40164 = IP not whitelisted)
  2. account/getaccountbasicinfo -> account type (service_type) + verify status (verify_type)
  3. draft/add (minimal probe)  -> validates draft capability; probe draft is deleted immediately

No article is ever published by this probe.
"""
import argparse
import json
import sys
import time

import requests

APPID_DEFAULT = ""
SECRET_DEFAULT = ""
API_BASE = "https://api.weixin.qq.com"


def load_credentials(appid: str, secret: str, account_name: str = "") -> tuple[str, str]:
    """Prefer CLI args; fall back to config.yaml wechat section (multi-account aware).

    Account resolution mirrors ncoda_common.get_wechat_account: --account <name>
    → wechat.accounts；缺省用默认账号（default/accounts 首项/旧字段）。
    """
    if appid and secret:
        return appid, secret
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    try:
        from ncoda_common import get_wechat_account, load_config
    except ImportError:
        print("ncoda_common 不可用（缺少 PyYAML?）；请用 --appid/--secret 显式传参", file=sys.stderr)
        return "", ""
    cfg = load_config()
    acc = get_wechat_account(cfg, account_name or None)
    if acc is None:
        return "", ""
    return acc["appid"], acc["secret"]


def get_token(appid: str, secret: str) -> str:
    resp = requests.get(f"{API_BASE}/cgi-bin/token",
                        params={"grant_type": "client_credential", "appid": appid, "secret": secret}, timeout=15)
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"token: errcode={data.get('errcode')} errmsg={data.get('errmsg')}")
    return data["access_token"]


def account_basic_info(token: str) -> dict:
    resp = requests.get(f"{API_BASE}/cgi-bin/account/getaccountbasicinfo",
                        params={"access_token": token}, timeout=15)
    return resp.json()


SERVICE_TYPE = {0: "订阅号", 1: "订阅号(历史老账号升级)", 2: "服务号"}
VERIFY_TYPE = {-1: "未认证", 0: "微信认证(已认证)", 1: "新浪微博认证",
               2: "腾讯微博认证", 3: "已资质认证通过但未通过名称认证",
               4: "已资质认证通过、未通过名称认证", 5: "已资质认证通过、未通过名称认证"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--appid", default="")
    ap.add_argument("--secret", default="")
    ap.add_argument("--account", default="", help="目标公众号名（config.yaml wechat.accounts 中的 name）")
    ap.add_argument("--no-draft", action="store_true", help="skip step 3 (draft/add probe)")
    args = ap.parse_args()

    appid, secret = load_credentials(args.appid, args.secret, args.account)
    if not appid or not secret:
        print("缺少 appid/secret：请用 --appid/--secret 或填写 config.yaml 的 wechat 段（--account 可指定账号）")
        return 2

    print("== Step 1: access_token ==")
    try:
        token = get_token(appid, secret)
        print("  OK: 凭证有效，IP 白名单已放行")
    except RuntimeError as e:
        print(f"  FAIL: {e}")
        if "40164" in str(e):
            print("  → 需要登录 mp.weixin.qq.com → 设置与开发 → 基本配置 → IP白名单，")
            print("    把当前出口 IP 加入白名单后重跑本脚本")
        return 1

    print("== Step 2: 账号类型 ==")
    try:
        info = account_basic_info(token)
        if "errcode" in info and info["errcode"] != 0:
            print(f"  FAIL: errcode={info['errcode']} errmsg={info.get('errmsg')}")
        else:
            st = info.get("service_type", "?")
            vt = info.get("verify_type", "?")
            nickname = info.get("nickname", "?")
            print(f"  昵称: {nickname}")
            print(f"  类型: {SERVICE_TYPE.get(st, st)} (service_type={st})")
            print(f"  认证: {VERIFY_TYPE.get(vt, vt)} (verify_type={vt})")
            verified = isinstance(vt, int) and vt in (0, 1, 2)
            print("  → freepublish(API直发) 权限:", "✅ 有（认证账号）" if verified else "❌ 无（2025-07起个人/未认证无 freepublish，报 48001）")
            print("  → 建议发布通道:", "L2: freepublish API直发" if verified else "L1: draft/add → 后台人工发布")
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL: {e}")

    if args.no_draft:
        return 0

    print("== Step 3: draft/add 探测（随后立即删除探测草稿） ==")
    try:
        body = {"articles": [{"title": "__probe__", "author": "", "digest": "",
                              "content": "<p>probe</p>", "show_cover_pic": 0}]}
        resp = requests.post(f"{API_BASE}/cgi-bin/draft/add", params={"access_token": token},
                             data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                             headers={"Content-Type": "application/json; charset=utf-8"}, timeout=15)
        data = resp.json()
        if data.get("errcode", 0) != 0:
            print(f"  FAIL: errcode={data.get('errcode')} errmsg={data.get('errmsg')}")
            return 1
        media_id = data["media_id"]
        print(f"  OK: draft/add 可用 (media_id={media_id})，立即删除")
        time.sleep(1)
        d = requests.post(f"{API_BASE}/cgi-bin/draft/delete", params={"access_token": token},
                          json={"media_id": media_id}, timeout=15).json()
        print(f"  清理: {d}")
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL: {e}")
        return 1

    print("\n探测完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
