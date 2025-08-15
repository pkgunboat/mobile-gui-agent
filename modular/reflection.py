"""
反思模块
"""

import base64
import json
import time
from typing import Dict, List, Any, Optional

from .models import model_manager
from .utils import calculate_image_similarity

class ReflectionManager:
    """反思管理器"""
    
    def __init__(self):
        self.model_manager = model_manager
    
    def summarize_execution_history(self, messages: List[Dict[str, Any]]) -> str:
        """总结ui-tars的执行历史，提取关键信息"""
        summary = []
        
        for i, msg in enumerate(messages):
            if msg["role"] == "user" and isinstance(msg["content"], list):
                # 用户消息包含截图
                summary.append(f"步骤{i+1}: 用户提供截图")
            elif msg["role"] == "assistant":
                # 助手回复
                content = msg["content"]
                if "Thought:" in content and "Action:" in content:
                    # 提取思考和动作
                    thought_part = content.split("Action:")[0].replace("Thought:", "").strip()
                    action_part = content.split("Action:")[1].strip()
                    summary.append(f"步骤{i+1}: 思考: {thought_part[:100]}... | 动作: {action_part[:100]}...")
                else:
                    summary.append(f"步骤{i+1}: {content[:100]}...")
        
        return "\n".join(summary)
    
    def reflect_on_execution(self, original_instruction: str, current_subtask: str, 
                           messages: List[Dict[str, Any]], current_screenshot_path: str,
                           action_history: Optional[List[Dict[str, Any]]] = None,
                           completed_subtasks: Optional[List[str]] = None,
                           all_subtasks: Optional[List[Dict[str, Any]]] = None,
                           task_logger=None) -> Dict[str, Any]:
        """对当前子任务的执行过程进行反思"""
        try:
            # 编码当前截图
            with open(current_screenshot_path, "rb") as f:
                base64_img = base64.b64encode(f.read()).decode('utf-8')
            
            # 总结执行历史
            execution_summary = self.summarize_execution_history(messages)
            
            # 总结子任务期间完成的动作
            action_summary = ""
            if action_history:
                action_summary = "子任务期间完成的动作：\n"
                for i, action in enumerate(action_history):
                    action_summary += f"步骤{i+1}: {action['action_type']} - {action.get('thought', '无思考过程')}\n"
            else:
                action_summary = "暂无动作历史记录"
            
            # 检查是否是总任务完成检查
            if current_subtask.startswith("请检查用户的总任务是否已经完成"):
                # 总任务完成检查，直接使用提供的提示词
                reflection_prompt = current_subtask
            else:
                # 构建反思提示词
                reflection_prompt = f"""
你是一个GUI-Agent领域任务执行反思专家。请基于以下信息对当前GUI-Agent的子任务的执行过程进行反思：

## 总体任务
{original_instruction}

## 完整子任务计划
"""
                
                # 添加完整子任务计划信息
                if all_subtasks:
                    reflection_prompt += "完整的子任务计划：\n"
                    for i, subtask in enumerate(all_subtasks, 1):
                        reflection_prompt += f"{i}. {subtask['description']}\n"
                else:
                    reflection_prompt += "无完整子任务计划信息\n"
                
                reflection_prompt += f"""
## 已完成子任务
"""
                
                if completed_subtasks:
                    reflection_prompt += "\n".join([f"- {subtask}" for subtask in completed_subtasks])
                else:
                    reflection_prompt += "无已完成子任务"
                
                reflection_prompt += f"""

## 当前子任务
{current_subtask}

## 子任务期间完成的动作
{action_summary}

## ui-tars执行历史总结
{execution_summary}

## 当前界面截图
[图片已提供]

请进行以下分析：

### 1. 总结子任务期间完成的动作
分析ui-tars-agent在当前子任务中执行了哪些动作，这些动作是否符合子任务的目标。

### 2. 判断当前子任务是否完成
仔细分析当前界面是否已经达到子任务的目标，判断子任务是否完成。

### 3. 结合动作判断是否需要重新规划
判断标准：
1. **是否存在重复的无效动作**：ui-tars-agent在同一界面尝试多次相同的动作但无效，说明当前子任务对ui-tars-agent来说太难或者子任务不合理，应该重新规划。
2. **是否偏离或超出了原计划**：ui-tars-agent可能做出不符合当前子任务的动作，或者已经顺势完成了后续的一些子任务，则需要重新进行规划以便可以衔接到当前的状态。
3. **计划合理性**: 如果觉得后续子任务的计划不合理，请重新规划。

请以JSON格式返回：
{{
    "subtask_completed": true/false,
    "action_summary": "动作总结",
    "current_issues": ["问题1", "问题2"],
    "suggestions": ["建议1", "建议2"],
    "reflection_summary": "反思总结",
    "need_replanning": true/false,
    "replanning_reason": "重新规划的原因"
}}
"""
            
            # 构建包含完整message历史的对话
            reflection_messages = [
                {
                    "role": "system",
                    "content": "你是一个任务执行反思专家，负责分析当前子任务的执行过程并提供改进建议。"
                }
            ]
            
            # 添加ui-tars的完整message历史（限制长度避免token过多）
            if messages:
                recent_messages = messages[-6:] if len(messages) > 6 else messages
                for msg in recent_messages:
                    reflection_messages.append(msg)
            
            # 添加当前截图和反思提示
            reflection_messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": reflection_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpg;base64,{base64_img}"}}
                ]
            })
            
            reflection_start_time = time.time()
            reflection_result = self.model_manager.call_reflection_model(reflection_messages)
            reflection_execution_time = time.time() - reflection_start_time
            print(f"Reflection result: {reflection_result}")
            
            # 记录反思模型调用
            if task_logger:
                task_logger.log_model_call(
                    model_name=self.model_manager.config["reflection_model"],
                    call_type="reflection",
                    input_data={"original_instruction": original_instruction, "current_subtask": current_subtask, "messages_count": len(reflection_messages)},
                    output_data={"reflection_result": reflection_result},
                    execution_time=reflection_execution_time,
                    success=True
                )
            
            # 尝试解析JSON结果
            try:
                # 清理可能的markdown格式
                cleaned_result = reflection_result.strip()
                if cleaned_result.startswith("```json"):
                    cleaned_result = cleaned_result[7:]
                if cleaned_result.endswith("```"):
                    cleaned_result = cleaned_result[:-3]
                cleaned_result = cleaned_result.strip()
                
                print(f"Attempting to parse JSON: {cleaned_result[:200]}...")
                reflection_data = json.loads(cleaned_result)
                
                # 确保所有必需字段都存在
                required_fields = {
                    "subtask_completed": False,
                    "action_summary": "",
                    "current_issues": [],
                    "suggestions": [],
                    "reflection_summary": "",
                    "need_replanning": False,
                    "replanning_reason": ""
                }
                
                # 补充缺失的字段
                for field, default_value in required_fields.items():
                    if field not in reflection_data:
                        reflection_data[field] = default_value
                    elif field == "current_issues" and not isinstance(reflection_data[field], list):
                        if isinstance(reflection_data[field], str):
                            reflection_data[field] = [reflection_data[field]]
                        else:
                            reflection_data[field] = []
                    elif field == "suggestions" and not isinstance(reflection_data[field], list):
                        if isinstance(reflection_data[field], str):
                            reflection_data[field] = [reflection_data[field]]
                        else:
                            reflection_data[field] = []
                    elif field == "action_summary" and not isinstance(reflection_data[field], str):
                        reflection_data[field] = str(reflection_data[field]) if reflection_data[field] is not None else ""
                
                print(f"Successfully parsed reflection data: {reflection_data}")
                
                # 记录反思完成
                if task_logger:
                    task_logger.log_reflection(reflection_data, reflection_execution_time)
                
                return reflection_data
            except json.JSONDecodeError as e:
                print(f"JSON parsing failed: {e}")
                print(f"Raw reflection result: {reflection_result}")
                # 如果JSON解析失败，返回默认结构
                return {
                    "subtask_completed": False,
                    "action_summary": "",
                    "current_issues": ["无法解析反思结果"],
                    "suggestions": ["重新规划任务"],
                    "reflection_summary": reflection_result,
                    "need_replanning": True,
                    "replanning_reason": "反思结果解析失败"
                }
                
        except Exception as e:
            print(f"Reflection failed: {e}")
            return {
                "subtask_completed": False,
                "action_summary": "",
                "current_issues": ["反思过程出错"],
                "suggestions": ["重新规划任务"],
                "reflection_summary": f"反思失败: {e}",
                "need_replanning": True,
                "replanning_reason": "反思过程出错"
            }
    
    def check_total_task_completion_with_all_screenshots(self, original_instruction: str, 
                                                        total_task_check_prompt: str,
                                                        completed_subtasks: List[str], 
                                                        subtask_list: List[Dict[str, Any]], 
                                                        task_logger) -> Dict[str, Any]:
        """基于所有保存的截图检查总任务完成情况"""
        try:
            # 获取所有保存的截图
            all_screenshots = task_logger.get_all_screenshots()
            
            if not all_screenshots:
                print("No screenshots available for total task completion check")
                return {
                    "subtask_completed": False,
                    "task_analysis": "No screenshots available",
                    "missing_steps": ["无法获取截图"],
                    "reflection_summary": "无法进行任务完成检查"
                }
            
            # 构建包含所有截图的提示词
            enhanced_prompt = f"""
{total_task_check_prompt}

## 任务执行过程中的所有截图
以下是任务执行过程中的所有截图，按时间顺序排列：
"""
            
            # 添加所有截图到消息中
            messages = [
                {
                    "role": "system",
                    "content": "你是一个任务完成检查专家，负责基于任务执行过程中的所有截图来判断总任务是否已经完成。"
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": enhanced_prompt}
                    ]
                }
            ]
            
            # 添加所有截图
            for i, screenshot_path in enumerate(all_screenshots):
                if os.path.exists(screenshot_path):
                    with open(screenshot_path, "rb") as f:
                        base64_img = base64.b64encode(f.read()).decode('utf-8')
                    
                    messages[1]["content"].append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpg;base64,{base64_img}"}
                    })
            
            # 调用反思模型
            reflection_start_time = time.time()
            reflection_result = self.model_manager.call_reflection_model(messages)
            reflection_execution_time = time.time() - reflection_start_time
            print(f"Total task completion check result: {reflection_result}")
            
            # 记录模型调用
            if task_logger:
                task_logger.log_model_call(
                    model_name=self.model_manager.config["reflection_model"],
                    call_type="total_task_completion_check",
                    input_data={"original_instruction": original_instruction, "screenshots_count": len(all_screenshots)},
                    output_data={"reflection_result": reflection_result},
                    execution_time=reflection_execution_time,
                    success=True
                )
            
            # 尝试解析JSON结果
            try:
                # 清理可能的markdown格式
                cleaned_result = reflection_result.strip()
                if cleaned_result.startswith("```json"):
                    cleaned_result = cleaned_result[7:]
                if cleaned_result.endswith("```"):
                    cleaned_result = cleaned_result[:-3]
                cleaned_result = cleaned_result.strip()
                
                print(f"Attempting to parse JSON: {cleaned_result[:200]}...")
                reflection_data = json.loads(cleaned_result)
                
                # 确保所有必需字段都存在
                required_fields = {
                    "subtask_completed": False,
                    "task_analysis": "",
                    "missing_steps": [],
                    "completion_evidence": "",
                    "reflection_summary": ""
                }
                
                # 补充缺失的字段
                for field, default_value in required_fields.items():
                    if field not in reflection_data:
                        reflection_data[field] = default_value
                    elif field == "missing_steps" and not isinstance(reflection_data[field], list):
                        if isinstance(reflection_data[field], str):
                            reflection_data[field] = [reflection_data[field]]
                        else:
                            reflection_data[field] = []
                
                print(f"Successfully parsed total task completion check data: {reflection_data}")
                return reflection_data
                
            except json.JSONDecodeError as e:
                print(f"JSON parsing failed: {e}")
                print(f"Raw reflection result: {reflection_result}")
                return {
                    "subtask_completed": False,
                    "task_analysis": "无法解析检查结果",
                    "missing_steps": ["解析失败"],
                    "reflection_summary": reflection_result
                }
                
        except Exception as e:
            print(f"Total task completion check failed: {e}")
            return {
                "subtask_completed": False,
                "task_analysis": f"检查过程出错: {e}",
                "missing_steps": ["检查失败"],
                "reflection_summary": f"检查失败: {e}"
            }

# 全局反思管理器实例
reflection_manager = ReflectionManager() 