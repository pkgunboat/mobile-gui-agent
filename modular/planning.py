"""
规划模块
"""

import base64
import re
import time
from typing import Dict, List, Any, Optional

from .models import model_manager
from .knowledge import knowledge_manager

class PlanningManager:
    """规划管理器"""
    
    def __init__(self):
        self.model_manager = model_manager
        self.knowledge_manager = knowledge_manager
    
    def decompose_task_to_subtasks(self, user_instruction: str, task_logger=None) -> List[Dict[str, Any]]:
        """调用VLM将用户指令分解为子任务列表"""
        # 1. 获取当前界面截图
        from .actions import action_executor
        screenshot_path, size_x, size_y = action_executor.screenshot(task_logger=task_logger, description="Task decomposition")
        if not screenshot_path:
            return []
        
        # 2. 编码截图
        with open(screenshot_path, "rb") as f:
            base64_img = base64.b64encode(f.read()).decode('utf-8')
        
        # 3. 获取任务相关知识（在任务分解时就获取，后续保持不变）
        task_knowledge = self.knowledge_manager.get_task_knowledge(user_instruction)
        
        # 记录任务知识到日志
        if task_logger:
            task_logger.log_task_knowledge(task_knowledge)
        
        return self._decompose_with_knowledge(user_instruction, task_knowledge, base64_img, task_logger)
    
    def _decompose_with_knowledge(self, user_instruction: str, task_knowledge: str, 
                                base64_img: str, task_logger=None) -> List[Dict[str, Any]]:
        """使用已知的task_knowledge进行任务分解"""
        messages = [
            {
                "role": "system",
                "content": f"""你是GUI-Agent领域的任务分解专家，需基于当前界面截图和用户指令，将任务拆分为多个连续的子任务，将子任务交给ui-tars-agent顺序之后可以完成用户的指令。

## 任务相关知识
{task_knowledge}

## ui-tars-agent可执行的动作类型
ui-tars-agent可以执行以下动作：
1. 点击指定坐标
2. 输入文本
3. 拖拽
4. 长按指定坐标
5. 点击Home键
6. 点击返回键

请确保生成的子任务只使用这些动作类型。

返回格式为：
[
    {{
        "subtask_id": 1,
        "description": "子任务的具体目标（如"打开浏览器""点击搜索框"）",
    }},
    {{
        "subtask_id": 2,
        "description": "子任务的具体目标（如"打开浏览器""点击搜索框"）",
    }},
    ...
]

要求：
- 子任务按执行顺序排列，前一个完成后才能执行下一个
- 任务描述要简洁明确，为可执行的子任务（比如"打开浏览器"，而不是"检查浏览器是否打开"、"如果操作之后没有变化xxx"）
- 确保子任务只使用ui-tars-agent支持的动作类型
- 考虑任务相关知识来制定更准确的子任务
- 由于子任务执行时并不知道用户的指令，所以子任务的目标设计应包含目标明确的终止条件 避免用模糊的方式描述子任务的目标，比如应该避免使用（在店铺菜谱中选择目标菜品）这种描述，因为子任务执行时并不知道用户的目标菜品是什么
- 如果知识中存在注意点，则需要将注意点作为子任务的一部分
- **重要：子任务描述要包含足够的限定信息以避免歧义**
  - 例如：说"在微信中搜索联系人"而不是"搜索联系人"
  - 例如：说"在相册应用中打开最新截图"而不是"打开最新截图"
  - 例如：说"在设置中打开壁纸选项"而不是"打开壁纸选项"
  - 例如：说"在微信聊天界面发送消息"而不是"发送消息"
- 直接返回列表，不要额外文字
"""
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"总体任务：{user_instruction}"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpg;base64,{base64_img}"}}
                ]
            }
        ]
        
        # 4. 调用VLM生成子任务列表
        try:
            decompose_start_time = time.time()
            response_text = self.model_manager.call_plan_model(messages)
            decompose_execution_time = time.time() - decompose_start_time
            print(f"Plan Agent Response:\n{response_text}")
            
            # 记录任务分解模型调用
            if task_logger:
                task_logger.log_model_call(
                    model_name=self.model_manager.config["plan_model"],
                    call_type="plan",
                    input_data={"user_instruction": user_instruction, "messages_count": len(messages)},
                    output_data={"response_text": response_text},
                    execution_time=decompose_execution_time,
                    success=True
                )
            
            # 5. 解析为Python列表（移除可能的格式符号）
            response_text = re.sub(r"```json|```", "", response_text).strip()
            subtasks = eval(response_text)  # 安全场景下可用json.loads，需确保输出严格为JSON
            
            # 确保返回的是列表格式
            if isinstance(subtasks, list):
                print(f"任务分解完成，生成 {len(subtasks)} 个子任务")
                return subtasks
            else:
                print(f"任务分解结果不是列表格式: {type(subtasks)}")
                return []
        
        except Exception as e:
            print(f"任务分解失败：{e}")
            if task_logger:
                task_logger.log_model_call(
                    model_name=self.model_manager.config["plan_model"],
                    call_type="plan",
                    input_data={"user_instruction": user_instruction, "messages_count": len(messages)},
                    output_data={},
                    execution_time=0,
                    success=False,
                    error=str(e)
                )
            return []
    
    def regenerate_plan(self, original_instruction: str, reflection_data: Dict[str, Any], 
                       completed_subtasks: List[str], current_screenshot_path: str, 
                       failed_subtask: Optional[str] = None, task_logger=None, 
                       task_knowledge: Optional[str] = None) -> List[Dict[str, Any]]:
        """使用plan-agent根据反思结果重新生成计划"""
        try:
            # 编码当前截图
            with open(current_screenshot_path, "rb") as f:
                base64_img = base64.b64encode(f.read()).decode('utf-8')
            
            # 如果没有提供task_knowledge，则获取任务相关知识
            if task_knowledge is None:
                task_knowledge = self.knowledge_manager.get_task_knowledge(original_instruction)
            
            # 构建计划重新生成提示词
            plan_prompt = f"""
你是GUI-Agent领域的任务分解专家，需基于当前界面截图和用户指令，将任务拆分为多个连续的子任务，将子任务交给ui-tars-agent顺序之后可以完成用户的指令。

## 总体任务
{original_instruction}

## 任务相关知识
{task_knowledge}

## 反思结果
{reflection_data['reflection_summary']}
当前问题: {', '.join(reflection_data.get('current_issues', []))}
建议: {', '.join(reflection_data.get('suggestions', []))}
重新规划原因: {reflection_data.get('replanning_reason', '未知')}

## 已完成子任务
{completed_subtasks}

## 失败的子任务（如果适用）
{failed_subtask if failed_subtask else "无"}

## ui-tars-agent可执行的动作类型
ui-tars-agent可以执行以下动作：
1. click(point='<point>x y</point>') - 点击指定坐标
2. type(content='text') - 输入文本，提交时在末尾加"\\n"
3. drag(start_point='<point>x1 y1</point>', end_point='<point>x2 y2</point>') - 从起点拖拽到终点
4. press_home() - 点击Home键
5. press_back() - 点击返回键
6. finished(content='xxx') - 任务完成

## 当前界面截图
[图片已提供]

请重新规划剩余的子任务，确保能够完成总体任务。

要求：
- 子任务按执行顺序排列，前一个完成后才能执行下一个
- 任务描述要简洁明确，为可执行的子任务（比如"打开浏览器"，而不是"检查浏览器是否打开"、"如果操作之后没有变化xxx"）
- 确保子任务只使用ui-tars-agent支持的动作类型
- 考虑任务相关知识来制定更准确的子任务
- 如果知识中存在注意点，则需要将注意点作为子任务的一部分
- **重要：子任务描述要包含足够的限定信息以避免歧义**
  - 例如：说"在微信中搜索联系人"而不是"搜索联系人"
  - 例如：说"在相册应用中打开最新截图"而不是"打开最新截图"
  - 例如：说"在设置中打开壁纸选项"而不是"打开壁纸选项"
  - 例如：说"在微信聊天界面发送消息"而不是"发送消息"
- 避免重复已完成的子任务
- 基于当前界面状态制定计划
- 考虑反思中提到的具体问题
- 如果某个子任务失败，考虑用不同的方法重新尝试
- 优先考虑反思中提到的建议

返回格式为：
[
    {{
        "subtask_id": 1,
        "description": "子任务描述",
    }},
    ...
]
"""
            
            messages = [
                {
                    "role": "system",
                    "content": "你是任务规划专家，负责基于反思结果重新生成任务计划。"
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": plan_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpg;base64,{base64_img}"}}
                    ]
                }
            ]
            
            plan_start_time = time.time()
            plan_result = self.model_manager.call_plan_model(messages)
            plan_execution_time = time.time() - plan_start_time
            print(f"Plan regeneration result: {plan_result}")
            
            # 记录计划重新生成模型调用
            if task_logger:
                task_logger.log_model_call(
                    model_name=self.model_manager.config["plan_model"],
                    call_type="plan",
                    input_data={"original_instruction": original_instruction, "reflection_data": reflection_data, "completed_subtasks": completed_subtasks},
                    output_data={"plan_result": plan_result},
                    execution_time=plan_execution_time,
                    success=True
                )
            
            # 尝试解析计划结果
            try:
                plan_result = re.sub(r"```json|```", "", plan_result).strip()
                new_subtasks = eval(plan_result)
                
                # 确保返回的是列表格式
                if isinstance(new_subtasks, list):
                    # 记录计划重新生成完成
                    if task_logger:
                        task_logger.log_plan_regeneration(
                            old_plan=[],
                            new_plan=new_subtasks,
                            reason=reflection_data.get('replanning_reason', 'Unknown'),
                            execution_time=plan_execution_time
                        )
                    return new_subtasks
                else:
                    print(f"Plan result is not a list: {type(new_subtasks)}")
                    return []
            except Exception as e:
                print(f"Plan parsing failed: {e}")
                return []
                
        except Exception as e:
            print(f"Plan regeneration failed: {e}")
            return []

# 全局规划管理器实例
planning_manager = PlanningManager() 