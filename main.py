from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core.utils.session_waiter import session_waiter, SessionController
import astrbot.api.message_components as Comp
import random


@register("gal_game", "YourName", "Galgame告白场景插件", "1.0.0")
class GalGamePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 可以在这里初始化一些游戏数据
        self.characters = ["樱花", "小夜", "莉香", "美雪"]  # 可随机选择的女主角

    @filter.command("gal挑战")
    async def start_gal_game(self, event: AstrMessageEvent):
        """开始GalGame告白场景"""
        try:
            # 随机选择一位女主角
            heroine = random.choice(self.characters)

            # 生成初始场景
            initial_scene = await self.generate_scene(
                f"生成一个{heroine}向男主告白的场景开场，提供两个选项让男主选择如何回应"
            )

            # 发送初始场景
            yield event.plain_result(f"【{heroine}的告白】\n{initial_scene}")

            # 启动会话控制器
            @session_waiter(timeout=120, record_history_chains=False)
            async def game_session(controller: SessionController, event: AstrMessageEvent):
                # 获取用户选择
                choice = event.message_str.strip()

                if choice in ["1", "2"]:
                    # 根据选择生成后续剧情
                    next_scene = await self.generate_scene(
                        f"根据选择{choice}继续{heroine}的告白场景，提供新的选项或走向结局"
                    )

                    # 检查是否到达结局
                    if "结局" in next_scene or "成功" in next_scene or "失败" in next_scene:
                        await event.send(event.plain_result(f"【结局】\n{next_scene}"))
                        controller.stop()
                    else:
                        await event.send(event.plain_result(next_scene))
                        controller.keep(timeout=120, reset_timeout=True)
                else:
                    await event.send(event.plain_result("请选择1或2来继续游戏"))
                    controller.keep(timeout=120, reset_timeout=True)

            # 启动会话
            await game_session(event)

        except Exception as e:
            logger.error(f"GalGame error: {str(e)}")
            yield event.plain_result("游戏发生错误，请稍后再试")

    async def generate_scene(self, prompt: str) -> str:
        """调用大模型生成场景"""
        try:
            # 获取当前使用的LLM提供商
            provider = self.context.get_using_provider()
            if not provider:
                return "无法连接到AI服务，请检查配置"

            # 调用LLM生成场景
            llm_response = await provider.text_chat(
                prompt=prompt,
                session_id=None,
                contexts=[],
                image_urls=[],
                system_prompt="你是一个galgame剧本作家，请生成浪漫的告白场景和选项。每次回复应包含场景描述和1-2个选项。选项用数字标记，如1. xxx 2. xxx",
            )

            if llm_response.role == "assistant":
                return llm_response.completion_text
            else:
                return "生成场景时发生错误"

        except Exception as e:
            logger.error(f"Generate scene error: {str(e)}")
            return "生成场景时发生错误"

    async def terminate(self):
        """插件卸载时调用"""
        pass
