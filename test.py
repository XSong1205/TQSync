#!/usr/bin/env python3
"""
测试脚本
用于测试各个组件的基本功能
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from utils.logger import setup_logger, get_logger
from utils.config import get_config
from utils.media_handler import get_media_handler
from utils.retry_manager import get_retry_manager
from utils.filter_prefix import get_filter_prefix_handler
from utils.forward_parser import get_forward_parser
from bots.telegram_bot import get_telegram_bot
from bots.qq_bot import get_qq_bot

logger = get_logger()

async def test_config():
    """测试配置加载"""
    print("🔍 测试配置加载...")
    try:
        config = get_config()
        telegram_config = config.get_telegram_config()
        qq_config = config.get_qq_config()
        
        print(f"✅ Telegram Token: {'已配置' if telegram_config['token'] else '未配置'}")
        print(f"✅ Telegram Chat ID: {telegram_config['chat_id']}")
        print(f"✅ QQ WebSocket URL: {qq_config['ws_url']}")
        print(f"✅ QQ Group ID: {qq_config['group_id']}")
        
        if config.validate_config():
            print("✅ 配置验证通过")
            return True
        else:
            print("❌ 配置验证失败")
            return False
            
    except Exception as e:
        print(f"❌ 配置测试失败: {e}")
        return False

async def test_telegram_proxy():
    """测试Telegram代理配置"""
    print("\n🔍 测试Telegram代理配置...")
    try:
        config = get_config()
        proxy_config = config.get('telegram.proxy', {})
        
        if not proxy_config.get('enable', False):
            print("ℹ️  Telegram代理未启用，跳过代理测试")
            return True
        
        proxy_type = proxy_config.get('type', 'socks5')
        proxy_host = proxy_config.get('host', '127.0.0.1')
        proxy_port = proxy_config.get('port', 1080)
        
        print(f"📡 代理配置: {proxy_type}://{proxy_host}:{proxy_port}")
        
        # 测试代理连接
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((proxy_host, proxy_port))
        sock.close()
        
        if result == 0:
            print("✅ 代理服务器连接正常")
            return True
        else:
            print("❌ 无法连接到代理服务器")
            return False
            
    except Exception as e:
        print(f"❌ 代理测试失败: {e}")
        return False

async def test_telegram_connection():
    """测试Telegram连接"""
    print("\n🔍 测试Telegram连接...")
    try:
        telegram_bot = await get_telegram_bot()
        await telegram_bot.initialize()
        
        # 测试发送消息
        success = await telegram_bot.send_message("我操，TG端居然连上了。（bot.main.telegram_bot.core.send_message success）")
        if success:
            print("✅ Telegram连接测试成功")
            return True
        else:
            print("❌ Telegram消息发送失败")
            return False
            
    except Exception as e:
        print(f"❌ Telegram连接测试失败: {e}")
        return False

async def test_qq_connection():
    """测试QQ连接"""
    print("\n🔍 测试QQ连接...")
    try:
        qq_bot = await get_qq_bot()
        
        # 测试发送消息
        success = await qq_bot.send_group_message("我操，QQ端竟然连上了。（bot.main.qq_bot.core.napcat.api.send_group_message success）")
        if success:
            print("✅ QQ连接测试成功")
            return True
        else:
            print("❌ QQ消息发送失败")
            return False
            
    except Exception as e:
        print(f"❌ QQ连接测试失败: {e}")
        return False

async def test_media_handler():
    """测试媒体处理器"""
    print("\n🔍 测试媒体处理器...")
    try:
        media_handler = await get_media_handler()
        await media_handler.initialize()
        
        print("✅ 媒体处理器初始化成功")
        return True
        
    except Exception as e:
        print(f"❌ 媒体处理器测试失败: {e}")
        return False

async def test_retry_manager():
    """测试重试管理器"""
    print("\n🔍 测试重试管理器...")
    try:
        retry_manager = await get_retry_manager()
        await retry_manager.initialize()
        
        # 测试添加消息到队列
        test_message = {
            'type': 'text',
            'text': '测试重试消息'
        }
        await retry_manager.add_to_retry_queue(test_message, "测试错误")
        
        # 获取队列统计
        stats = await retry_manager.get_queue_stats()
        print(f"✅ 重试队列统计: {stats}")
        
        return True
        
    except Exception as e:
        print(f"❌ 重试管理器测试失败: {e}")
        return False

async def test_filter_prefix():
    """测试过滤前缀处理器"""
    print("\n🔍 测试过滤前缀处理器...")
    try:
        filter_handler = get_filter_prefix_handler()
        
        # 测试命令解析
        test_message = {
            'text': '!ping 测试',
            'platform': 'telegram'
        }
        
        command_info = filter_handler.extract_command(test_message)
        if command_info:
            print(f"✅ 命令解析成功: {command_info['command']}")
            
            # 测试命令处理
            response = await filter_handler.handle_command(command_info)
            print(f"✅ 命令响应: {response}")
        
        return True
        
    except Exception as e:
        print(f"❌ 过滤前缀处理器测试失败: {e}")
        return False

async def test_forward_parser():
    """测试转发消息解析器"""
    print("\n🔍 测试转发消息解析器...")
    try:
        forward_parser = get_forward_parser()
        
        # 测试转发消息判断
        test_message = {
            'raw_data': {
                'message': [
                    {
                        'type': 'forward',
                        'data': {
                            'content': [
                                {
                                    'nickname': '测试用户',
                                    'user_id': '123456',
                                    'time': 1700000000,
                                    'message': [{'type': 'text', 'data': {'text': '测试消息'}}]
                                }
                            ]
                        }
                    }
                ]
            }
        }
        
        is_forward = forward_parser.is_forward_message(test_message)
        print(f"✅ 转发消息检测: {is_forward}")
        
        if is_forward:
            # 测试解析
            parsed_messages = forward_parser.parse_forward_message(test_message)
            if parsed_messages:
                print(f"✅ 解析到 {len(parsed_messages)} 条转发消息")
                
                # 测试格式化
                formatted = forward_parser.format_for_telegram(parsed_messages)
                print(f"✅ 格式化为Telegram消息: {len(formatted)} 条")
        
        return True
        
    except Exception as e:
        print(f"❌ 转发消息解析器测试失败: {e}")
        return False

async def run_tests():
    """运行所有测试"""
    print("=" * 50)
    print("🤖 Telegram-QQ机器人测试脚本")
    print("=" * 50)
    
    # 配置日志
    setup_logger("INFO")
    
    # 运行各项测试
    tests = [
        ("配置测试", test_config),
        ("Telegram代理测试", test_telegram_proxy),
        ("Telegram连接测试", test_telegram_connection),
        ("QQ连接测试", test_qq_connection),
        ("媒体处理器测试", test_media_handler),
        ("重试管理器测试", test_retry_manager),
        ("过滤前缀处理器测试", test_filter_prefix),
        ("转发消息解析器测试", test_forward_parser)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name}执行出错: {e}")
            results.append((test_name, False))
    
    # 输出测试结果
    print("\n" + "=" * 50)
    print("📊 测试结果汇总:")
    print("=" * 50)
    
    passed = 0
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n总计: {passed}/{len(results)} 项测试通过")
    
    if passed == len(results):
        print("🎉 所有测试通过！机器人可以正常运行。")
    else:
        print("⚠️  部分测试失败，请检查配置和网络连接。")
    
    return passed == len(results)

if __name__ == "__main__":
    try:
        success = asyncio.run(run_tests())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"测试过程中发生错误: {e}")
        sys.exit(1)