#!/usr/bin/env python3
"""检查服务器认证配置状态"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from lightrag.utils import get_env_value

# 加载.env文件
load_dotenv(dotenv_path=".env", override=False)

print("="*60)
print("认证配置检查")
print("="*60)

auth_accounts = get_env_value("AUTH_ACCOUNTS", "")
token_secret = get_env_value("TOKEN_SECRET", "")

print(f"\n从环境变量读取：")
print(f"AUTH_ACCOUNTS: {repr(auth_accounts)}")
print(f"TOKEN_SECRET: {repr(token_secret)}")

if not auth_accounts or auth_accounts.strip() == "":
    print("\n✅ 认证未配置 - 服务器应该允许Guest访问（无需登录）")
    print("\n如果仍然要求登录，请：")
    print("1. 完全停止服务器（Ctrl+C 或 kill进程）")
    print("2. 确认.env文件中AUTH_ACCOUNTS被注释掉")
    print("3. 重新启动服务器")
else:
    print(f"\n⚠️  认证已配置 - 需要登录")
    print(f"配置的账户：{auth_accounts}")
    print("\n请使用以下账户登录：")
    accounts = auth_accounts.split(",")
    for account in accounts:
        if ":" in account:
            username, password = account.split(":", 1)
            print(f"  用户名: {username}, 密码: {password}")

print("\n" + "="*60)
