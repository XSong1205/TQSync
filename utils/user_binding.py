"""
用户绑定管理模块
负责QQ和Telegram用户之间的双向绑定功能
"""

import asyncio
import time
import random
import string
from typing import Dict, Any, Optional
from utils.logger import get_logger
from utils.database import get_db_manager

logger = get_logger()

class UserBindingManager:
    """用户绑定管理器"""
    
    def __init__(self):
        """初始化绑定管理器"""
        # 存储验证码信息 {verification_code: {qq_user_id, tg_user_id, expire_time, attempts}}
        self.pending_verifications = {}
        
        # 存储已绑定的用户关系 {qq_user_id: tg_user_id, tg_user_id: qq_user_id}
        self.bindings = {}
        
        # 存储用户绑定元数据 {user_id: {bind_time, last_active, platform}}
        self.binding_metadata = {}
        
        # 验证码有效期（秒）
        self.verification_ttl = 600  # 10分钟
        
        # 最大验证尝试次数
        self.max_attempts = 3
        
        # 清理任务
        self.cleanup_task = None
        
        # 数据库管理器
        self.db_manager = None
    
    async def initialize_database(self):
        """初始化数据库并加载现有数据"""
        try:
            self.db_manager = get_db_manager()
            
            # 加载现有的绑定数据
            existing_bindings = self.db_manager.get_all_bindings()
            for binding in existing_bindings:
                qq_user_id = binding['qq_user_id']
                tg_user_id = binding['tg_user_id']
                
                # 建立内存中的双向映射
                self.bindings[qq_user_id] = tg_user_id
                self.bindings[tg_user_id] = qq_user_id
                
                # 加载元数据
                self.binding_metadata[qq_user_id] = {
                    'bind_time': binding['bind_time'],
                    'last_active': binding['last_active'],
                    'platform': 'qq'
                }
                self.binding_metadata[tg_user_id] = {
                    'bind_time': binding['bind_time'],
                    'last_active': binding['last_active'],
                    'platform': 'telegram'
                }
            
            logger.info(f"从数据库加载了 {len(existing_bindings)} 个绑定关系")
            
        except Exception as e:
            logger.error(f"初始化数据库失败: {e}")
    
    async def start_cleanup_task(self):
        """启动清理过期验证码的任务"""
        self.cleanup_task = asyncio.create_task(self._cleanup_expired_verifications())
    
    async def stop_cleanup_task(self):
        """停止清理任务"""
        if self.cleanup_task and not self.cleanup_task.done():
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
    
    async def _cleanup_expired_verifications(self):
        """定期清理过期的验证码"""
        while True:
            try:
                current_time = time.time()
                expired_codes = []
                
                # 找出过期的验证码
                for code, info in self.pending_verifications.items():
                    if current_time > info['expire_time']:
                        expired_codes.append(code)
                
                # 清理过期验证码
                for code in expired_codes:
                    del self.pending_verifications[code]
                    logger.info(f"清理过期验证码: {code}")
                
                # 每30秒检查一次
                await asyncio.sleep(30)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"清理过期验证码时出错: {e}")
                await asyncio.sleep(30)
    
    def _generate_verification_code(self) -> str:
        """生成8位验证码（数字+大写字母）"""
        characters = string.ascii_uppercase + string.digits
        return ''.join(random.choices(characters, k=8))
    
    def _is_verification_expired(self, verification_info: Dict[str, Any]) -> bool:
        """检查验证码是否过期"""
        return time.time() > verification_info['expire_time']
    
    async def initiate_binding(self, platform: str, user_id: str) -> Dict[str, Any]:
        """
        发起绑定流程
        
        Args:
            platform: 平台名称 ('qq' 或 'telegram')
            user_id: 用户ID
            
        Returns:
            Dict: 包含验证码和相关信息的字典
        """
        try:
            # 检查用户是否已经绑定
            if self.is_user_bound(platform, user_id):
                return {
                    'success': False,
                    'error': 'already_bound',
                    'message': '⚠️ 您已绑定账号，如需解绑请使用!unbind'
                }
            
            # 清理该用户之前的待验证记录
            codes_to_remove = []
            for code, info in self.pending_verifications.items():
                if ((platform == 'qq' and info.get('qq_user_id') == user_id) or
                    (platform == 'telegram' and info.get('tg_user_id') == user_id)):
                    codes_to_remove.append(code)
            
            for code in codes_to_remove:
                del self.pending_verifications[code]
            
            # 生成新的验证码
            verification_code = self._generate_verification_code()
            
            # 创建验证信息
            verification_info = {
                'qq_user_id': user_id if platform == 'qq' else None,
                'tg_user_id': user_id if platform == 'telegram' else None,
                'expire_time': time.time() + self.verification_ttl,
                'attempts': 0,
                'created_time': time.time()
            }
            
            self.pending_verifications[verification_code] = verification_info
            
            logger.info(f"为{platform.upper()}用户 {user_id} 生成验证码: {verification_code}")
            
            return {
                'success': True,
                'verification_code': verification_code,
                'expires_in': self.verification_ttl,
                'message': f"已生成验证码，请在另一平台发送 !bind {verification_code} 完成绑定"
            }
            
        except Exception as e:
            logger.error(f"发起绑定流程时出错: {e}")
            return {
                'success': False,
                'error': 'internal_error',
                'message': '❌ 系统错误，请稍后重试'
            }
    
    async def complete_binding(self, platform: str, user_id: str, verification_code: str) -> Dict[str, Any]:
        """
        完成绑定流程
        
        Args:
            platform: 平台名称 ('qq' 或 'telegram')
            user_id: 用户ID
            verification_code: 验证码
            
        Returns:
            Dict: 绑定结果
        """
        try:
            # 检查验证码是否存在
            if verification_code not in self.pending_verifications:
                return {
                    'success': False,
                    'error': 'invalid_code',
                    'message': '❌ 验证码错误，请检查是否输入正确'
                }
            
            verification_info = self.pending_verifications[verification_code]
            
            # 检查验证码是否过期
            if self._is_verification_expired(verification_info):
                del self.pending_verifications[verification_code]
                return {
                    'success': False,
                    'error': 'expired',
                    'message': '❌ 验证码已过期，请重新生成'
                }
            
            # 检查验证尝试次数
            if verification_info['attempts'] >= self.max_attempts:
                del self.pending_verifications[verification_code]
                return {
                    'success': False,
                    'error': 'too_many_attempts',
                    'message': '❌ 验证失败次数过多，验证码已失效'
                }
            
            # 确定另一个平台的用户ID
            if platform == 'qq':
                other_platform = 'telegram'
                other_user_id = verification_info['tg_user_id']
                qq_user_id = user_id
                tg_user_id = other_user_id
            else:  # telegram
                other_platform = 'qq'
                other_user_id = verification_info['qq_user_id']
                qq_user_id = other_user_id
                tg_user_id = user_id
            
            # 验证另一个平台的用户ID是否存在
            if not other_user_id:
                verification_info['attempts'] += 1
                return {
                    'success': False,
                    'error': 'incomplete_verification',
                    'message': '❌ 验证流程不完整，请重新开始绑定'
                }
            
            # 检查两个用户是否都已经绑定到其他账号
            if self.is_user_bound('qq', qq_user_id) or self.is_user_bound('telegram', tg_user_id):
                del self.pending_verifications[verification_code]
                return {
                    'success': False,
                    'error': 'already_bound',
                    'message': '❌ 其中一方账号已被绑定，请先解绑'
                }
            
            # 执行绑定
            bind_result = self._perform_binding(qq_user_id, tg_user_id)
            
            if bind_result['success']:
                # 清理验证码
                del self.pending_verifications[verification_code]
                logger.info(f"绑定成功: QQ({qq_user_id}) ↔ Telegram({tg_user_id})")
                
                return {
                    'success': True,
                    'message': '✅ 账号绑定成功！',
                    'qq_user_id': qq_user_id,
                    'tg_user_id': tg_user_id
                }
            else:
                return bind_result
                
        except Exception as e:
            logger.error(f"完成绑定流程时出错: {e}")
            return {
                'success': False,
                'error': 'internal_error',
                'message': '❌ 系统错误，请稍后重试'
            }
    
    def _perform_binding(self, qq_user_id: str, tg_user_id: str) -> Dict[str, Any]:
        """执行实际的绑定操作"""
        try:
            # 创建双向映射
            self.bindings[qq_user_id] = tg_user_id
            self.bindings[tg_user_id] = qq_user_id
            
            # 记录绑定元数据
            current_time = time.time()
            self.binding_metadata[qq_user_id] = {
                'bind_time': current_time,
                'last_active': current_time,
                'platform': 'qq'
            }
            self.binding_metadata[tg_user_id] = {
                'bind_time': current_time,
                'last_active': current_time,
                'platform': 'telegram'
            }
            
            # 保存到数据库
            if self.db_manager:
                metadata = {
                    'bind_time': current_time,
                    'last_active': current_time
                }
                db_success = self.db_manager.save_user_binding(qq_user_id, tg_user_id, metadata)
                if db_success:
                    logger.info(f"绑定关系已持久化到数据库: QQ({qq_user_id}) ↔ Telegram({tg_user_id})")
                else:
                    logger.warning(f"绑定关系数据库保存失败，但仍存在于内存中")
            
            return {
                'success': True,
                'message': '✅ 账号绑定成功！',
                'qq_user_id': qq_user_id,
                'tg_user_id': tg_user_id
            }
            
        except Exception as e:
            logger.error(f"执行绑定操作时出错: {e}")
            return {
                'success': False,
                'error': 'bind_failed',
                'message': '❌ 绑定失败，请稍后重试'
            }
    
    def is_user_bound(self, platform: str, user_id: str) -> bool:
        """检查用户是否已绑定"""
        return user_id in self.bindings
    
    def get_bound_user(self, platform: str, user_id: str) -> Optional[str]:
        """
        获取绑定的对方用户ID
        
        Args:
            platform: 当前平台
            user_id: 当前用户ID
            
        Returns:
            对方平台的用户ID，如果未绑定则返回None
        """
        if not self.is_user_bound(platform, user_id):
            return None
        
        bound_user_id = self.bindings.get(user_id)
        if not bound_user_id:
            return None
            
        # 验证绑定关系的一致性
        reverse_bound = self.bindings.get(bound_user_id)
        if reverse_bound != user_id:
            logger.warning(f"绑定关系不一致: {user_id} ↔ {bound_user_id}")
            return None
            
        return bound_user_id
    
    async def unbind_user(self, platform: str, user_id: str) -> Dict[str, Any]:
        """
        解绑用户
        
        Args:
            platform: 平台名称
            user_id: 用户ID
            
        Returns:
            解绑结果
        """
        try:
            # 检查用户是否已绑定
            if not self.is_user_bound(platform, user_id):
                return {
                    'success': False,
                    'error': 'not_bound',
                    'message': '⚠️ 您尚未绑定任何账号'
                }
            
            # 获取绑定的对方用户
            bound_user_id = self.get_bound_user(platform, user_id)
            if not bound_user_id:
                return {
                    'success': False,
                    'error': 'binding_corrupted',
                    'message': '❌ 绑定关系异常，请联系管理员'
                }
            
            # 执行解绑
            self.bindings.pop(user_id, None)
            self.bindings.pop(bound_user_id, None)
            self.binding_metadata.pop(user_id, None)
            self.binding_metadata.pop(bound_user_id, None)
            
            logger.info(f"解绑成功: {platform.upper()}({user_id}) ↔ 对方({bound_user_id})")
            
            return {
                'success': True,
                'message': '✅ 账号解绑成功！',
                'unbound_user': bound_user_id
            }
            
        except Exception as e:
            logger.error(f"解绑用户时出错: {e}")
            return {
                'success': False,
                'error': 'internal_error',
                'message': '❌ 系统错误，请稍后重试'
            }
    
    def get_binding_info(self, platform: str, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户的绑定信息"""
        try:
            if not self.is_user_bound(platform, user_id):
                return None
            
            bound_user_id = self.get_bound_user(platform, user_id)
            if not bound_user_id:
                return None
            
            metadata = self.binding_metadata.get(user_id, {})
            
            return {
                'bound': True,
                'current_platform': platform,
                'current_user_id': user_id,
                'bound_platform': 'telegram' if platform == 'qq' else 'qq',
                'bound_user_id': bound_user_id,
                'bind_time': metadata.get('bind_time'),
                'last_active': metadata.get('last_active')
            }
            
        except Exception as e:
            logger.error(f"获取绑定信息时出错: {e}")
            return None
    
    def update_last_active(self, platform: str, user_id: str):
        """更新用户最后活跃时间"""
        try:
            if user_id in self.binding_metadata:
                self.binding_metadata[user_id]['last_active'] = time.time()
        except Exception as e:
            logger.error(f"更新最后活跃时间时出错: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取绑定统计信息"""
        try:
            # 统计绑定对数（每对绑定涉及两个用户）
            binding_pairs = set()
            for user_id in self.bindings.keys():
                if user_id in self.bindings:
                    bound_user = self.bindings[user_id]
                    # 创建标准化的绑定对标识
                    pair = tuple(sorted([str(user_id), str(bound_user)]))
                    binding_pairs.add(pair)
            
            total_bindings = len(binding_pairs)
            pending_verifications = len(self.pending_verifications)
            
            # 统计各平台绑定用户数
            qq_binded_users = len([k for k in self.bindings.keys() if str(k).isdigit()])
            tg_binded_users = len([k for k in self.bindings.keys() if not str(k).isdigit()])
            
            return {
                'total_bindings': total_bindings,
                'pending_verifications': pending_verifications,
                'qq_binded_users': qq_binded_users,
                'telegram_binded_users': tg_binded_users
            }
            
        except Exception as e:
            logger.error(f"获取绑定统计时出错: {e}")
            return {
                'total_bindings': 0,
                'pending_verifications': 0,
                'qq_binded_users': 0,
                'telegram_binded_users': 0
            }

# 全局实例
user_binding_manager = UserBindingManager()

async def get_user_binding_manager() -> UserBindingManager:
    """获取用户绑定管理器实例"""
    return user_binding_manager