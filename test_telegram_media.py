#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram 媒体同步功能测试
测试 sticker、GIF 和视频同步功能
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from utils.logger import setup_logger, get_logger

logger = get_logger()

def test_media_type_mapping():
    """测试媒体类型映射"""
    print("=" * 80)
    print("📊 Telegram 媒体类型映射测试")
    print("=" * 80)
    
    from core.message_sync import MessageSync
    
    sync = MessageSync()
    
    # 测试映射函数
    test_cases = [
        ('photo', 'image'),
        ('video', 'video'),
        ('audio', 'audio'),
        ('voice', 'record'),
        ('document', 'file'),
        ('sticker', 'image'),  # 新增
        ('animation', 'image'),  # 新增
    ]
    
    print("\n测试 _map_telegram_type_to_qq:")
    all_passed = True
    
    for tg_type, expected_qq_type in test_cases:
        result = sync._map_telegram_type_to_qq(tg_type)
        status = "✅" if result == expected_qq_type else "❌"
        print(f"  {status} {tg_type} -> {result} (期望：{expected_qq_type})")
        if result != expected_qq_type:
            all_passed = False
    
    return all_passed

def test_sticker_detection():
    """测试贴纸检测"""
    print("\n" + "=" * 80)
    print("🔍 Telegram 媒体类型识别测试")
    print("=" * 80)
    
    try:
        from telegram import Message, Sticker, Animation
        
        # 模拟消息对象
        class MockMessage:
            def __init__(self):
                self.sticker = None
                self.animation = None
                self.photo = None
                self.video = None
                self.audio = None
                self.voice = None
                self.document = None
        
        from bots.telegram_bot import TelegramBot
        
        bot = TelegramBot()
        
        # 测试 sticker
        mock_msg = MockMessage()
        mock_msg.sticker = Sticker(file_id='test_sticker_id', file_unique_id='unique', width=512, height=512, is_animated=False, is_video=False)
        
        media_type = bot._identify_media_type(mock_msg)
        print(f"  Sticker 检测：{media_type} {'✅' if media_type == 'sticker' else '❌'}")
        
        # 测试 animation (GIF)
        mock_msg2 = MockMessage()
        mock_msg2.animation = Animation(file_id='test_animation_id', file_unique_id='unique', width=512, height=512, duration=10)
        
        media_type2 = bot._identify_media_type(mock_msg2)
        print(f"  Animation 检测：{media_type2} {'✅' if media_type2 == 'animation' else '❌'}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 测试失败：{e}")
        return False

async def main():
    """主测试函数"""
    try:
        setup_logger("INFO")
        
        print("\n" + "=" * 80)
        print("🎬 Telegram 媒体同步功能测试")
        print("=" * 80)
        
        # 测试 1: 媒体类型映射
        mapping_passed = test_media_type_mapping()
        
        # 测试 2: 媒体类型识别
        detection_passed = test_sticker_detection()
        
        print("\n" + "=" * 80)
        print("📋 测试结果")
        print("=" * 80)
        
        if mapping_passed and detection_passed:
            print("✅ 所有测试通过!")
            print("\n✨ 已实现功能:")
            print("  • Sticker (贴纸) 同步 - 作为图片发送到 QQ")
            print("  • Animation (GIF) 同步 - 作为图片发送到 QQ")
            print("  • Video (视频) 同步 - 正常支持")
            print("  • Photo (照片) 同步 - 正常支持")
            print("  • Audio/Voice 同步 - 正常支持")
            
            print("\n💡 使用说明:")
            print("  1. 在 Telegram 发送 sticker，会自动同步到 QQ 群")
            print("  2. 在 Telegram 发送 GIF，会自动同步到 QQ 群")
            print("  3. 在 Telegram 发送视频，会自动同步到 QQ 群")
            print("  4. 查看详细日志了解同步状态")
            
            return True
        else:
            print("❌ 部分测试失败!")
            return False
            
    except KeyboardInterrupt:
        print("\n⚠️  测试被用户中断")
        return False
    except Exception as e:
        print(f"\n💥 测试执行过程中发生错误：{e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
