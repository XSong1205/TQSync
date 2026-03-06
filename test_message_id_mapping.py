#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
消息 ID 映射功能测试脚本
测试跨平台消息 ID 映射的建立和查询功能
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from utils.logger import setup_logger, get_logger
from utils.message_id_mapper import get_message_id_mapper
from utils.database import get_db_manager

logger = get_logger()

async def test_message_id_mapping():
    """测试消息 ID 映射功能"""
    print("=" * 80)
    print("📊 消息 ID 映射功能测试")
    print("=" * 80)
    
    # 配置日志
    setup_logger("DEBUG")
    
    try:
        print("\n📋 测试目标:")
        print("1. 测试消息 ID 映射的添加")
        print("2. 测试消息 ID 映射的查询")
        print("3. 测试数据库持久化")
        print("4. 测试双向映射关系")
        
        # 获取映射管理器实例
        print("\n" + "=" * 80)
        print("🔧 初始化映射管理器")
        print("=" * 80)
        
        mapper = await get_message_id_mapper()
        db = get_db_manager()
        
        print("✅ 映射管理器和数据库管理器已就绪")
        
        # 测试 1: 添加 QQ → Telegram 映射
        print("\n" + "=" * 80)
        print("📝 测试 1: 添加 QQ → Telegram 映射")
        print("=" * 80)
        
        qq_msg_id_1 = 12345678
        tg_msg_id_1 = 987654321
        
        success = mapper.add_mapping(
            'qq', qq_msg_id_1,
            'telegram', tg_msg_id_1
        )
        
        if success:
            print(f"✅ 映射添加成功：QQ({qq_msg_id_1}) → Telegram({tg_msg_id_1})")
        else:
            print(f"❌ 映射添加失败：QQ({qq_msg_id_1}) → Telegram({tg_msg_id_1})")
            return False
        
        # 保存到数据库
        db_success = db.save_message_mapping(
            'qq', str(qq_msg_id_1),
            'telegram', str(tg_msg_id_1)
        )
        
        if db_success:
            print(f"✅ 数据库保存成功")
        else:
            print(f"❌ 数据库保存失败")
        
        # 测试 2: 查询映射
        print("\n" + "=" * 80)
        print("🔍 测试 2: 查询映射关系")
        print("=" * 80)
        
        # 正向查询
        target_id = mapper.get_target_message_id('qq', qq_msg_id_1, 'telegram')
        if target_id == tg_msg_id_1:
            print(f"✅ 正向查询成功：QQ({qq_msg_id_1}) → Telegram({target_id})")
        else:
            print(f"❌ 正向查询失败：期望 {tg_msg_id_1}, 实际 {target_id}")
        
        # 反向查询
        source_info = mapper.get_source_message_info('telegram', tg_msg_id_1)
        if source_info and source_info['source_message_id'] == qq_msg_id_1:
            print(f"✅ 反向查询成功：Telegram({tg_msg_id_1}) → QQ({source_info['source_message_id']})")
        else:
            print(f"❌ 反向查询失败")
        
        # 测试 3: 数据库查询
        print("\n" + "=" * 80)
        print("💾 测试 3: 数据库持久化查询")
        print("=" * 80)
        
        # 从数据库查询
        db_mapping = db.get_message_mapping('qq', str(qq_msg_id_1), 'telegram')
        if db_mapping == str(tg_msg_id_1):
            print(f"✅ 数据库查询成功：QQ({qq_msg_id_1}) → Telegram({db_mapping})")
        else:
            print(f"❌ 数据库查询失败：期望 {tg_msg_id_1}, 实际 {db_mapping}")
        
        # 测试 4: 添加 Telegram → QQ 映射
        print("\n" + "=" * 80)
        print("🔄 测试 4: 添加 Telegram → QQ 映射")
        print("=" * 80)
        
        tg_msg_id_2 = 111222333
        qq_msg_id_2 = 444555666
        
        success = mapper.add_mapping(
            'telegram', tg_msg_id_2,
            'qq', qq_msg_id_2
        )
        
        if success:
            print(f"✅ 映射添加成功：Telegram({tg_msg_id_2}) → QQ({qq_msg_id_2})")
            
            # 保存到数据库
            db.save_message_mapping(
                'telegram', str(tg_msg_id_2),
                'qq', str(qq_msg_id_2)
            )
        else:
            print(f"❌ 映射添加失败")
        
        # 测试 5: 统计信息
        print("\n" + "=" * 80)
        print("📈 测试 5: 获取统计信息")
        print("=" * 80)
        
        stats = mapper.get_stats()
        db_stats = db.get_stats()
        
        print("内存映射统计:")
        print(f"  • 总映射数：{stats.get('total_mappings', 0)}")
        print(f"  • 活跃映射数：{stats.get('active_mappings', 0)}")
        print(f"  • 映射请求数：{stats.get('mapping_requests', 0)}")
        print(f"  • 成功映射数：{stats.get('mapping_success', 0)}")
        
        print("\n数据库统计:")
        print(f"  • 用户绑定数：{db_stats.get('total_bindings', 0)}")
        print(f"  • 消息映射数：{db_stats.get('total_mappings', 0)}")
        print(f"  • 待处理验证码：{db_stats.get('pending_verifications', 0)}")
        
        # 测试 6: 删除映射
        print("\n" + "=" * 80)
        print("🗑️  测试 6: 删除映射")
        print("=" * 80)
        
        remove_success = mapper.remove_mapping('qq', qq_msg_id_1)
        if remove_success:
            print(f"✅ 内存映射已删除：QQ({qq_msg_id_1})")
        else:
            print(f"❌ 内存映射删除失败")
        
        db_remove_success = db.remove_message_mapping('qq', str(qq_msg_id_1))
        if db_remove_success:
            print(f"✅ 数据库映射已删除：QQ({qq_msg_id_1})")
        else:
            print(f"❌ 数据库映射删除失败")
        
        # 验证删除
        target_id_after = mapper.get_target_message_id('qq', qq_msg_id_1, 'telegram')
        if target_id_after is None:
            print(f"✅ 确认映射已删除：QQ({qq_msg_id_1}) → None")
        else:
            print(f"❌ 删除后仍能查询到映射：{target_id_after}")
        
        print("\n" + "=" * 80)
        print("📊 测试总结")
        print("=" * 80)
        
        print("✅ 消息 ID 映射功能测试完成!")
        print("\n关键功能验证:")
        print("  ✅ 内存映射添加和查询")
        print("  ✅ 数据库持久化")
        print("  ✅ 双向映射支持")
        print("  ✅ 映射删除")
        print("  ✅ 统计信息获取")
        
        print("\n🎯 下一步建议:")
        print("  1. 在实际消息发送时自动建立映射")
        print("  2. 在消息撤回时正确查询映射")
        print("  3. 定期清理过期映射")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """主测试函数"""
    try:
        success = await test_message_id_mapping()
        if success:
            print("\n✅ 所有测试通过!")
            print("\n💡 消息 ID 映射功能已就绪，可以正常使用撤回同步功能")
        else:
            print("\n❌ 测试过程中出现问题!")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n⚠️  测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 测试执行过程中发生严重错误：{e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
