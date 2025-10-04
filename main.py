from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core.utils.session_waiter import session_waiter, SessionController
import astrbot.api.message_components as Comp
import random
import asyncio

@register("gal_game", "YourName", "Galgame告白场景插件", "1.0.0")
class GalGamePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.characters = ["樱花", "小夜", "莉香", "美雪"]
        # 存储游戏状态：群ID -> 游戏数据
        self.game_states = {}
        
    @filter.command("gal告白")
    async def start_gal_game(self, event: AstrMessageEvent):
        """开始GalGame告白场景"""
        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("请在群聊中使用此功能")
            return
            
        # 检查是否已有游戏在进行中
        if group_id in self.game_states:
            yield event.plain_result("当前群聊已有游戏进行中，请等待结束或使用 /gal结束 结束当前游戏")
            return
            
        try:
            # 初始化游戏状态
            heroine = random.choice(self.characters)
            self.game_states[group_id] = {
                "heroine": heroine,
                "mood": 50,  # 初始好感度
                "scene_count": 0,
                "in_progress": True
            }
            
            # 生成初始场景
            initial_scene = await self.generate_scene(
                f"生成一个{heroine}向男主告白的场景开场。{heroine}的性格是害羞但真诚的。"
                "请描述场景、氛围和{heroine}的对话，但不要提供选项。"
            )
            
            # 发送初始场景
            yield event.plain_result(f"【{heroine}的告白】\n{initial_scene}")
            yield event.plain_result("现在，群友们可以自由发言，尝试回应{heroine}的告白！")
            
            # 启动会话控制器，监听群友的回应
            @session_waiter(timeout=300, record_history_chains=False)
            async def game_session(controller: SessionController, event: AstrMessageEvent):
                # 只处理同一群聊的消息
                if event.get_group_id() != group_id:
                    return
                    
                # 获取用户输入
                user_input = event.message_str.strip()
                
                # 更新游戏状态
                self.game_states[group_id]["scene_count"] += 1
                
                # 调用LLM评估用户输入并生成后续剧情
                next_scene = await self.generate_scene(
                    f"在之前的场景中，{heroine}向男主告白。"
                    f"现在男主回应：'{user_input}'。"
                    f"请生成{heroine}的反应和后续发展。"
                    f"当前{heroine}的好感度是{self.game_states[group_id]['mood']}（满分100）。"
                    "如果好感度>=80，导向告白成功的好结局；如果好感度<=30，导向告白失败的坏结局。"
                    "如果还未达到结局条件，请继续发展剧情。"
                )
                
                # 解析LLM响应，提取好感度变化和结局信息
                mood_change, is_ending = self.parse_llm_response(next_scene)
                
                # 更新好感度
                self.game_states[group_id]["mood"] += mood_change
                self.game_states[group_id]["mood"] = max(0, min(100, self.game_states[group_id]["mood"]))
                
                # 发送剧情发展
                mood_display = f"\n\n【{heroine}的好感度: {self.game_states[group_id]['mood']}/100】"
                await event.send(event.plain_result(next_scene + mood_display))
                
                # 检查是否达到结局
                if is_ending or self.game_states[group_id]["scene_count"] >= 10:  # 最多10轮
                    if self.game_states[group_id]["mood"] >= 80:
                        ending = await self.generate_scene(f"生成{heroine}告白成功的好结局场景")
                        await event.send(event.plain_result(f"🎉【Happy Ending】🎉\n{ending}"))
                    elif self.game_states[group_id]["mood"] <= 30:
                        ending = await self.generate_scene(f"生成{heroine}告白失败的坏结局场景")
                        await event.send(event.plain_result(f"💔【Bad Ending】💔\n{ending}"))
                    else:
                        ending = await self.generate_scene(f"生成{heroine}的普通结局场景")
                        await event.send(event.plain_result(f"【Normal Ending】\n{ending}"))
                    
                    # 结束游戏
                    del self.game_states[group_id]
                    controller.stop()
                else:
                    # 继续游戏
                    controller.keep(timeout=300, reset_timeout=True)
            
            # 启动会话
            await game_session(event)
            
        except Exception as e:
            logger.error(f"GalGame error: {str(e)}")
            if group_id in self.game_states:
                del self.game_states[group_id]
            yield event.plain_result("游戏发生错误，已结束当前游戏")

    @filter.command("gal结束")
    async def end_gal_game(self, event: AstrMessageEvent):
        """强制结束当前GalGame"""
        group_id = event.get_group_id()
        if group_id in self.game_states:
            del self.game_states[group_id]
            yield event.plain_result("已结束当前GalGame")
        else:
            yield event.plain_result("当前没有进行中的GalGame")

    async def generate_scene(self, prompt: str) -> str:
        """调用大模型生成场景"""
        try:
            # 获取当前使用的LLM提供商
            provider = self.context.get_using_provider()
            if not provider:
                return "无法连接到AI服务，请检查配置"
            
            # 构建系统提示词，确保LLM理解我们的需求
            system_prompt = (
                "你是一个galgame剧本作家，请生成浪漫的告白场景。"
                "请根据用户输入生成女主角的反应和后续剧情发展。"
                "请在内心评估好感度变化（±5到±20），但不要在回复中明确写出数字。"
                "当好感度达到80以上时，导向告白成功的好结局；"
                "当好感度降到30以下时，导向告白失败的坏结局。"
            )
            
            # 调用LLM生成场景
            llm_response = await provider.text_chat(
                prompt=prompt,
                session_id=None,
                contexts=[],
                image_urls=[],
                system_prompt=system_prompt,
            )
            
            if llm_response.role == "assistant":
                return llm_response.completion_text
            else:
                return "生成场景时发生错误"
                
        except Exception as e:
            logger.error(f"Generate scene error: {str(e)}")
            return "生成场景时发生错误"
    
    def parse_llm_response(self, response: str) -> (int, bool):
        """
        解析LLM响应，估算好感度变化和是否达到结局
        这是一个简化的实现，实际中可以更复杂
        """
        # 根据关键词估算好感度变化
        positive_keywords = ["开心", "高兴", "喜欢", "感动", "微笑", "脸红"]
        negative_keywords = ["失望", "伤心", "难过", "生气", "皱眉", "离开"]
        
        mood_change = 0
        is_ending = False
        
        # 检查正面关键词
        for keyword in positive_keywords:
            if keyword in response:
                mood_change += 5
                
        # 检查负面关键词
        for keyword in negative_keywords:
            if keyword in response:
                mood_change -= 5
                
        # 检查结局关键词
        ending_keywords = ["结局", "最后", "最终", "告别", "离开"]
        for keyword in ending_keywords:
            if keyword in response:
                is_ending = True
                break
                
        return mood_change, is_ending

    async def terminate(self):
        """插件卸载时调用"""
        # 清理所有游戏状态
        self.game_states.clear()
