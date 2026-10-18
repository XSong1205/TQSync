"""db/database.py 的功能回归测试（改动数据库层后必须跑）。

用法:
    python scripts/test_database.py

使用临时数据库，不影响真实 db/tqsync.db。全部断言通过时输出 PASS。
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import Database  # noqa: E402

_checks = 0


def check(cond, msg):
    global _checks
    _checks += 1
    if not cond:
        raise AssertionError(f"FAIL: {msg}")
    print(f"  ok - {msg}")


async def run() -> None:
    tmpdir = tempfile.mkdtemp(prefix="tqsync_test_db_")
    d = Database()
    d.db_path = os.path.join(tmpdir, "t.db")

    try:
        await d.init_db()
        await d.init_db()  # 幂等

        # ---- bindings ----
        print("[bindings]")
        check(await d.get_binding_by_qq(20001) is None, "未绑定时返回 None")
        await d.add_binding(10001, 20001, "alice", "爱丽丝")
        row = await d.get_binding_by_tg(10001)
        check(row is not None and row[1] == 20001, "add_binding 后可按 tg 查到")
        check((await d.get_binding_by_qq(20001))[0] == 10001, "按 qq 查到（含缓存命中路径）")
        check((await d.get_binding_by_tg_username("ALICE"))[0] == 10001, "按用户名忽略大小写查到")
        uid = row[4]
        check(bool(uid), "自动生成 uid")
        check(await d.get_custom_prefix_by_uid(uid) is None, "默认无自定义前缀")
        await d.update_custom_prefix(uid, "前缀A")
        check(await d.get_custom_prefix_by_uid(uid) == "前缀A", "更新前缀生效（缓存已失效）")
        check((await d.get_binding_by_tg(10001))[5] == "前缀A", "绑定行缓存已失效")
        await d.delete_binding(tg_user_id=10001)
        check(await d.get_binding_by_tg(10001) is None, "删除绑定后查询为空（负缓存已失效）")
        check(await d.get_binding_by_qq(20001) is None, "按 qq 也为空")

        # ---- message mapping ----
        print("[message_mapping]")
        await d.save_message_mapping(1001, 2001, sender_tg_id=10001)
        check(await d.get_tg_msg_id_by_qq(2001) == 1001, "QQ->TG 映射")
        check(await d.get_qq_msg_id_by_tg(1001) == 2001, "TG->QQ 映射")
        check(await d.get_tg_msg_id_by_qq(9999) is None, "不存在的映射返回 None")
        await d.delete_mapping_by_tg(1001)
        check(await d.get_qq_msg_id_by_tg(1001) is None, "delete_mapping_by_tg 生效")
        await d.save_message_mapping(1002, 2002, sender_qq_id=20009)
        await d.delete_mapping_by_qq(2002)
        check(await d.get_tg_msg_id_by_qq(2002) is None, "delete_mapping_by_qq 生效")

        # 并发写入（验证共享连接在并发下不炸、不丢数据）
        await asyncio.gather(*[
            d.save_message_mapping(5000 + i, 6000 + i, sender_qq_id=20009)
            for i in range(50)
        ])
        found = 0
        for i in range(50):
            if await d.get_tg_msg_id_by_qq(6000 + i) == 5000 + i:
                found += 1
        check(found == 50, f"50 条并发写入全部可读回（实际 {found}）")

        # ---- settings / blocked words ----
        print("[settings / blocked_words]")
        check(await d.get_setting("not_exist", "dflt") == "dflt", "缺省设置返回默认值")
        await d.set_setting("k1", "v1")
        check(await d.get_setting("k1") == "v1", "设置写入后可读")
        await d.set_setting("k1", "v2")
        check(await d.get_setting("k1") == "v2", "设置覆盖后缓存失效")
        check(await d.get_blocked_words() == [], "屏蔽词默认空")
        check(await d.add_blocked_word("广告") is True, "新增屏蔽词")
        check(await d.add_blocked_word("广告") is False, "重复新增返回 False")
        check(await d.check_blocked_word_in_text("这里有广告内容") == "广告", "命中屏蔽词")
        check(await d.check_blocked_word_in_text("正常消息") is None, "未命中返回 None")
        check(await d.remove_blocked_word("广告") is True, "删除屏蔽词")
        check(await d.check_blocked_word_in_text("这里有广告内容") is None, "删除后不再命中")

        # ---- verification codes ----
        print("[verification_codes]")
        code = await d.create_verification_code(20001, expire_minutes=5)
        check(len(code) == 6 and code.isdigit(), "生成 6 位验证码")
        res = await d.verify_and_consume_code(code)
        check(res["valid"] and res["qq_user_id"] == 20001, "验证码验证通过")
        res2 = await d.verify_and_consume_code(code)
        check((not res2["valid"]) and res2["reason"] == "验证码已被使用", "验证码不可重复使用")
        check((await d.verify_and_consume_code("000000"))["valid"] is False, "无效验证码")
        code2 = await d.create_verification_code(20002, expire_minutes=5)
        await d.cleanup_user_codes(20002)
        check((await d.verify_and_consume_code(code2))["valid"] is False, "cleanup_user_codes 生效")
        await d.cleanup_expired_codes()

        # ---- plugin data ----
        print("[plugin_data]")
        await d.set_plugin_data("demo", "a", "1")
        await d.set_plugin_data("demo", "a", "2")
        check(await d.get_plugin_data("demo", "a") == "2", "plugin data upsert")
        check([r["key"] for r in await d.get_plugin_data("demo")] == ["a"], "plugin data 列表")
        check(await d.get_all_plugin_names() == ["demo"], "plugin 名称列表")
        await d.delete_plugin_data("demo", "a")
        check(await d.get_plugin_data("demo", "a") is None, "删除单个 plugin data")
        await d.set_plugin_data("demo", "b", "1")
        await d.delete_plugin_data("demo")
        check(await d.get_all_plugin_names() == [], "删除整个插件数据")

        # ---- notice mapping ----
        print("[notice_mapping]")
        check(await d.is_notice_synced("h1") is False, "未同步哈希返回 False")
        await d.record_synced_notice("qq", "h1", notice_id="n1", tg_message_id=777)
        check(await d.is_notice_synced("h1") is True, "is_notice_synced")
        check(await d.is_notice_id_synced("n1") is True, "is_notice_id_synced")
        check(await d.is_tg_msg_id_synced_notice(777) is True, "is_tg_msg_id_synced_notice")
        check(await d.get_all_synced_notice_hashes() == {"h1"}, "哈希集合")
        check(await d.get_all_synced_notice_ids() == {"n1"}, "notice id 集合")

        # ---- 兼容接口 & 关闭后重开 ----
        print("[compat / lifecycle]")
        async with d._Database__get_connection() as conn:
            cursor = await conn.execute('SELECT COUNT(*) FROM message_mapping')
            total = (await cursor.fetchone())[0]
        check(total >= 50, f"兼容短连接 COUNT 可用（{total}）")
        check(len(await d.get_all_bindings()) == 0, "get_all_bindings 可用")
        await d.close()
        await d.set_setting("after_close", "1")
        check(await d.get_setting("after_close") == "1", "close 后可自动重连")
        await d.close()

        print(f"\nPASS - {_checks} 项断言全部通过")
    finally:
        try:
            await d.close()
        except Exception:
            pass
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(run())
