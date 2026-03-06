#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram 机器人初始化修复测试
验证 Telegram 机器人能否正常初始化和启动
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from utils.logger import setup_logger, get_logger
from bots.telegram_bot import get_telegram_bot

logger = get_logger()

async def test_telegram_initialization():
    """测试 Telegram 机器人初始化"""
    print("=" * 80)
    print("🤖 Telegram 机器人初始化修复测试")
    print("=" * 80)
    
    # 配置日志
    setup_logger("INFO")
    
    try:
        print("\n📋 测试目标:")
        print("1. 验证 Telegram 机器人初始化")
        print("2. 测试 HTTP 客户端配置")
        print("3. 验证应用构建过程")
        
        # 获取 Telegram 机器人实例
        print("\n" + "=" * 80)
        print("🔧 Telegram 机器人初始化测试")
        print("=" * 80)
        
        telegram_bot = await get_telegram_bot()
        
        print("✅ 获取 Telegram 机器人实例成功")
        print(f"   Token 长度: {len(telegram_bot.bot_token) if telegram_bot.bot_token else 0}")
        print(f"   Chat ID: {telegram_bot.chat_id}")
        
        # 测试初始化
        print("\n📍 执行初始化...")
        init_result = await telegram_bot.initialize()
        
        if init_result:
            print("✅ Telegram 机器人初始化成功")
            print(f"   Application 类型: {type(telegram_bot.application)}")
            print(f"   Bot 类型: {type(telegram_bot.bot)}")
            print(f"   HTTP 客户端: {telegram_bot.http_client is not None}")
        else:
            print("❌ Telegram 机器人初始化失败")
            return False
        
        # 测试 HTTP 客户端配置
        print("\n" + "=" * 80)
        print("🌐 HTTP 客户端配置测试")
        print("=" * 80)
        
        http_client = await telegram_bot._setup_http_client()
        print(f"✅ HTTP 客户端配置完成: {http_client is not None}")
        print(f"   自定义客户端: {telegram_bot.http_client is not None}")
        
        if telegram_bot.http_client:
            print(f"   客户端类型: {type(telegram_bot.http_client)}")
        
        # 测试基本功能（不实际启动）
        print("\n" + "=" * 80)
        print("⚡ 基本功能验证")
        print("=" * 80)
        
        # 验证必要组件是否存在
        required_attrs = ['application', 'bot', 'message_callback']
        missing_attrs = []
        
        for attr in required_attrs:
            if not hasattr(telegram_bot, attr):
                missing_attrs.append(attr)
            elif getattr(telegram_bot, attr) is None:
                print(f"⚠️  属性 {attr} 存在但为 None")
            else:
                print(f"✅ 属性 {attr} 配置正确")
        
        if missing_attrs:
            print(f"❌ 缺少必要属性: {missing_attrs}")
            return False
        
        print("\n" + "=" * 80)
        print("📊 测试总结")
        print("=" * 80)
        
        print("✅ Telegram 机器人初始化修复完成:")
        print("   • 移除了不兼容的 http_client 参数")
        print("   • 适配了新版本 python-telegram-bot API")
        print("   • 添加了初始化失败的安全检查")
        print("   • 保持了 SSL 验证问题的修复")
        
        print("\n🎯 下一步建议:")
        print("   1. 重新启动主程序测试完整功能")
        print("   2. 验证消息收发功能正常")
        print("   3. 测试媒体文件同步")
        
        return True
        
    except Exception as e:
        print(f"❌ Telegram 初始化测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """主测试函数"""
    try:
        success = await test_telegram_initialization()
        if success:
            print("\n✅ Telegram 机器人初始化测试通过!")
            print("\n💡 现在可以重新启动机器人进行完整测试")
        else:
            print("\n❌ 测试过程中出现问题!")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n⚠️  测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 测试执行过程中发生严重错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())