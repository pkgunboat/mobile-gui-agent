"""
主要的代理模块
"""

import time
import base64
from typing import Dict, List, Any, Optional

from .config import Config
from .models import model_manager
from .actions import action_executor
from .utils import parse_action_to_structure_output
from .reflection import reflection_manager
from .planning import planning_manager

class MobileAgent:
    """移动代理主类"""
    
    def __init__(self):
        self.model_manager = model_manager
        self.action_executor = action_executor
        self.reflection_manager = reflection_manager
        self.planning_manager = planning_manager
    
    def run_gui_task(self, instruction: str, model_type: str = "qwen25vl", 
                    max_rounds: int = None, is_subtask: bool = True, 
                    original_instruction: Optional[str] = None, 
                    completed_subtasks: Optional[List[str]] = None, 
                    all_subtasks: Optional[List[Dict[str, Any]]] = None, 
                    task_logger=None, task_knowledge: Optional[str] = None):
        """执行GUI任务"""
        if max_rounds is None:
            max_rounds = Config.MAX_ROUNDS
            
        # 构建系统提示词
        system_prompt = Config.SYSTEM_PROMPT_TEMPLATE.format(
            current_subtask=instruction,
            final_goal="",
            language="Chinese",
            completed_subtasks="无")
        
        messages = [{"role": "user", "content": system_prompt}]
        print(messages)
        
        # 收集ui-tars-agent的截图文件列表用于重复检测
        ui_tars_screenshot_files = []
        ui_tars_action_count = 0  # 记录ui-tars-agent执行的动作数量
        
        action_history = []  # 记录执行历史
        operate_model_type = "simple"
        for rounds in range(max_rounds):
            if rounds <= 5:
                operate_model_type = "simple"
            else:
                operate_model_type = "plan"
            print(f"\n=== Round {rounds + 1}/{max_rounds} ===")
            # 1. 获取截图及尺寸
            screenshot_path, origin_w, origin_h = self.action_executor.screenshot(
                rounds, task_logger=task_logger, description=f"Round {rounds + 1}")
            if not screenshot_path:
                print("Failed to get screenshot after retries")
                
                # 检查服务健康状态
                if not self.action_executor.check_service_health():
                    print("Screenshot service appears to be down or unstable")
                    print("Please check:")
                    print("1. Is the server.py running?")
                    print("2. Is the Android device connected?")
                    print("3. Is ADB working properly?")
                    print("4. Are there any permission issues?")
                    
                    # 尝试重新连接
                    print("Attempting to reconnect...")
                    time.sleep(5)
                    if self.action_executor.check_service_health():
                        print("Service recovered, retrying screenshot...")
                        screenshot_path, origin_w, origin_h = self.action_executor.screenshot(rounds)
                        if not screenshot_path:
                            print("Still cannot get screenshot after recovery attempt")
                            return None
                    else:
                        print("Service recovery failed, exiting...")
                        return None
                else:
                    print("Service is healthy but screenshot still failed")
                    return None

            # 2. 编码截图并添加到对话
            with open(screenshot_path, "rb") as f:
                base64_img = base64.b64encode(f.read()).decode('utf-8')
            messages.append({
                "role": "user",
                "content": [{
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpg;base64,{base64_img}"}
                }]
            })

            # 3. 调用模型获取动作
            try:
                start_time = time.time()
                model_output = self.model_manager.call_main_model(messages, temperature=0.0, model_type=operate_model_type)
                execution_time = time.time() - start_time
                print(f"Model Output:\n{model_output}")
                
                # 记录模型调用
                if task_logger:
                    task_logger.log_model_call(
                        model_name=self.model_manager.config["model_id"],
                        call_type="ui_tars",
                        input_data={"messages": messages, "temperature": 0.0},
                        output_data={"response": model_output},
                        execution_time=execution_time,
                        success=True
                    )
                
                # 4. 先尝试直接解析ui-tars输出
                try:
                    parsed_actions = parse_action_to_structure_output(
                        text=model_output,
                        factor=Config.IMAGE_FACTOR,
                        origin_h=origin_h,
                        origin_w=origin_w,
                        model_type=model_type
                    )
                    if parsed_actions:
                        print("Direct parsing successful, using original output")
                        messages.append({"role": "assistant", "content": model_output})
                    else:
                        raise ValueError("No valid actions parsed")
                except Exception as parse_error:
                    print(f"Direct parsing failed: {parse_error}")
                    print("Calling format correction model...")
                    
                    # 5. 解析失败时调用格式更正模型
                    formatted_message = [
                        {
                            "role": "system",
                            "content": """你是一个格式标准化助手，负责将ui-tars的输出转换为严格符合指定格式的内容。请遵循以下规则：

                            ## 输出格式要求
                            必须严格按照以下结构输出，不可添加额外内容：
                            Thought: ...
                            Action: ...

                            plaintext
                            1. 「Thought:」后紧跟思考过程，需完整保留原始输出中的推理逻辑、操作意图和判断依据
                            2. 「Action:」后紧跟动作指令，必须使用指定的函数调用格式

                            ## 动作空间（仅允许使用以下函数）
                            - click(point='<point>x1 y1</point>')  # 点击坐标(x1,y1)
                            - type(content='')  # 输入文本，提交需在末尾加"\\n"
                            - drag(start_point='<point>x1 y1</point>', end_point='<point>x2 y2</point>')  # 从(x1,y1)拖拽至(x2,y2)
                            - long_press(point='<point>x1 y1</point>')  # 长按坐标(x1,y1)
                            - press_home()  # 点击Home键
                            - press_back()  # 点击返回键
                            - finished(content='xxx')  # 任务完成，content需用转义字符\\'、\\"、\\n确保Python可解析

                            ## 处理规则
                            1. 提取原始输出中的思考过程到「Thought:」，动作指令到「Action:」
                            2. 修正非法格式（如函数名错误、坐标缺失）为动作空间中的合法格式
                            3. 若缺少思考过程，不用补充，设置为None
                            4. 若缺少动作指令，基于思考过程从动作空间选择最合适的动作补充
                            5. 确保content中的特殊字符已正确转义（如单引号用\\'，换行用\\n）
                            6. 对于drag动作，保持start_point和end_point参数名不变
                            """
                        },
                        {
                            "role": "user",
                            "content": f"请处理以下ui-tars输出内容，转换为指定格式：{model_output}\n"
                        }
                    ]
                    
                    format_start_time = time.time()
                    formatted_model_output = self.model_manager.call_format_model(formatted_message)
                    format_execution_time = time.time() - format_start_time
                    print(f"formatted_model_output: {formatted_model_output}")
                    
                    # 记录格式更正模型调用
                    if task_logger:
                        task_logger.log_model_call(
                            model_name=self.model_manager.config["format_model"],
                            call_type="format",
                            input_data={"original_output": model_output, "messages": formatted_message},
                            output_data={"formatted_output": formatted_model_output},
                            execution_time=format_execution_time,
                            success=True
                        )
                    
                    # 6. 再次尝试解析更正后的输出
                    try:
                        parsed_actions = parse_action_to_structure_output(
                            text=formatted_model_output,
                            factor=Config.IMAGE_FACTOR,
                            origin_h=origin_h,
                            origin_w=origin_w,
                            model_type=model_type
                        )
                        if parsed_actions:
                            print("Format correction successful")
                            messages.append({"role": "assistant", "content": formatted_model_output})
                        else:
                            print("Format correction failed, no valid actions parsed")
                            return None
                    except Exception as format_error:
                        print(f"Format correction parsing failed: {format_error}")
                        return None
                        
            except Exception as e:
                print(f"Model call failed: {e}")
                if task_logger:
                    task_logger.log_model_call(
                        model_name=self.model_manager.config["model_id"],
                        call_type="ui_tars",
                        input_data={"messages": messages, "temperature": 0.0},
                        output_data={},
                        execution_time=0,
                        success=False,
                        error=str(e)
                    )
                return None

            # 7. 执行动作
            task_completed = False
            for action in parsed_actions:
                act_type = action["action_type"]
                act_inputs = action["action_inputs"]
                thought = action.get("thought", "")
                print(f"Execute action: {act_type} with inputs {act_inputs}")
                
                # 记录执行历史
                action_history.append({
                    "round": rounds + 1,
                    "action_type": act_type,
                    "action_inputs": act_inputs,
                    "thought": thought
                })
                
                # 记录动作执行开始
                action_start_time = time.time()

                # 处理点击动作（tap）
                if act_type in ["click", "tap"]:
                    start_box = act_inputs.get("start_box")
                    if isinstance(start_box, list) and len(start_box) >= 2:
                        print(start_box)
                        x = round(start_box[0])
                        y = round(start_box[1])
                        self.action_executor.tap(x, y)
                        time.sleep(1)

                # 处理输入动作（type）
                elif act_type == "type":
                    content = act_inputs.get("content", "")
                    if content:
                        self.action_executor.type_text(content)
                        time.sleep(1)

                # 处理滑动动作（slide/drag）
                elif act_type in ["slide", "drag"]:
                    start_box = act_inputs.get("start_box")
                    end_box = act_inputs.get("end_box")
                    
                    # 处理格式化模型可能产生的错误参数名
                    if start_box is None:
                        start_box = act_inputs.get("start_start_box")
                    if end_box is None:
                        end_box = act_inputs.get("end_start_box")
                    if start_box is None:
                        start_box = act_inputs.get("start_point")
                    if end_box is None:
                        end_box = act_inputs.get("end_point")
                    
                    print(f"Debug: start_box={start_box}, end_box={end_box}")
                    print(f"Debug: All act_inputs={act_inputs}")
                    
                    if start_box and end_box and len(start_box) >= 2 and len(end_box) >= 2:
                        # 处理字符串格式的坐标
                        if isinstance(start_box, str):
                            start_box = start_box.replace("(", "").replace(")", "").split(",")
                            start_box = [float(x.strip()) for x in start_box]
                        if isinstance(end_box, str):
                            end_box = end_box.replace("(", "").replace(")", "").split(",")
                            end_box = [float(x.strip()) for x in end_box]
                        
                        x1, y1 = round(start_box[0]), round(start_box[1])
                        x2, y2 = round(end_box[0]), round(end_box[1])
                        print(f"Debug: Executing slide from ({x1},{y1}) to ({x2},{y2})")
                        
                        # 检查坐标是否合理
                        if x1 < 0 or y1 < 0 or x2 < 0 or y2 < 0:
                            print(f"Warning: Invalid coordinates detected: ({x1},{y1}) to ({x2},{y2})")
                            continue
                        
                        if abs(x1 - x2) < 10 and abs(y1 - y2) < 10:
                            print(f"Warning: Slide distance too small: ({x1},{y1}) to ({x2},{y2})")
                            continue
                        
                        self.action_executor.slide(x1, y1, x2, y2)
                        time.sleep(2)
                    else:
                        print(f"Error: Invalid slide parameters - start_box: {start_box}, end_box: {end_box}")
                        continue

                # 处理长按动作（long_press）
                elif act_type == "long_press":
                    start_box = act_inputs.get("start_box")
                    if isinstance(start_box, list) and len(start_box) >= 2:
                        print(start_box)
                        x = round(start_box[0])
                        y = round(start_box[1])
                        # 使用slide实现长按（从同一点到同一点，持续时间1000ms）
                        self.action_executor.slide(x, y, x, y)
                        time.sleep(1)
                    else:
                        print(f"Error: Invalid long_press parameters - start_box: {start_box}")
                        continue

                # 处理返回/主页动作
                elif "back" in act_type:
                    self.action_executor.back()
                    time.sleep(1)
                elif "home" in act_type:
                    self.action_executor.home()
                    time.sleep(1)

                # 处理完成动作
                elif act_type == "finished":
                    print("Task completed!")
                    task_completed = True
                    # 记录动作执行完成
                    if task_logger:
                        task_logger.log_action_execution(
                            action_type=act_type,
                            action_inputs=act_inputs,
                            thought=thought,
                            execution_time=time.time() - action_start_time,
                            success=True
                        )
                    break

                # 未支持的动作
                else:
                    print(f"Unsupported action type: {act_type}")
                    if task_logger:
                        task_logger.log_action_execution(
                            action_type=act_type,
                            action_inputs=act_inputs,
                            thought=thought,
                            execution_time=time.time() - action_start_time,
                            success=False,
                            error="Unsupported action type"
                        )
                    continue
                
                # 记录动作执行完成（除了finished动作，因为finished已经在上面记录了）
                if task_logger and act_type != "finished":
                    task_logger.log_action_execution(
                        action_type=act_type,
                        action_inputs=act_inputs,
                        thought=thought,
                        execution_time=time.time() - action_start_time,
                        success=True
                    )
            
            # 8. 反思模块在第5步、第10步或任务完成时进行反思
            if is_subtask and original_instruction:
                should_reflect = False
                reflection_reason = ""
                
                # 判断是否需要进行反思
                if rounds == 5:  # 第6步
                    should_reflect = True
                    reflection_reason = "第6步反思"
                elif rounds == 9:  # 第10步（达到最大步数限制）
                    should_reflect = True
                    reflection_reason = "第10步反思（达到最大步数限制）"
                elif task_completed:  # ui-tars-agent判断任务完成
                    # 检查是否是ui-tars自己完成的（通过finished动作）
                    if any(action.get("action_type") == "finished" for action in parsed_actions):
                        should_reflect = False
                        reflection_reason = "ui-tars自己完成，跳过反思"
                    else:
                        should_reflect = True
                        reflection_reason = "任务完成反思"
                
                if should_reflect:
                    print(f"\n=== {reflection_reason} ===")
                    # 获取当前截图
                    screenshot_now_path, _, _ = self.action_executor.screenshot(
                        0, task_logger=task_logger, description=f"Reflection - {reflection_reason}")
                    if screenshot_now_path:
                        # 重命名截图为screenshot_now
                        import os
                        new_screenshot_path = "screenshot_now.jpg"
                        if os.path.exists(new_screenshot_path):
                            os.remove(new_screenshot_path)
                        os.rename(screenshot_now_path, new_screenshot_path)
                        print(f"反思截图保存为: {new_screenshot_path}")
                        # 将当前截图添加到ui-tars-agent的截图文件列表
                        ui_tars_screenshot_files.append(new_screenshot_path)
                        ui_tars_action_count += 1
                        # 进行反思
                        reflection_data = self.reflection_manager.reflect_on_execution(
                            original_instruction, instruction, messages, new_screenshot_path, 
                            action_history=action_history, completed_subtasks=completed_subtasks, 
                            all_subtasks=all_subtasks, task_logger=task_logger)
                    else:
                        print("无法获取反思截图，使用原截图进行反思")
                        reflection_data = self.reflection_manager.reflect_on_execution(
                            original_instruction, instruction, messages, screenshot_path, 
                            action_history=action_history, completed_subtasks=completed_subtasks, 
                            all_subtasks=all_subtasks, task_logger=task_logger)
                    if reflection_data.get("subtask_completed", False):
                        print("反思判断当前子任务已完成，退出执行")
                        return None
                    elif reflection_data.get("need_replanning", False):
                        print(f"反思判断需要重新规划：{reflection_data.get('replanning_reason', '未知原因')}")
                        new_subtasks = self.planning_manager.regenerate_plan(
                            original_instruction, reflection_data, completed_subtasks, 
                            new_screenshot_path, instruction, task_logger, task_knowledge)
                        if new_subtasks:
                            print(f"重新生成了 {len(new_subtasks)} 个子任务")
                            return new_subtasks
                        else:
                            print("重新生成计划失败")
                            return "FAILED"  # 返回特殊值表示失败
                    else:
                        print("反思判断子任务未完成，继续执行")
                        # === 新增功能：第6步反思建议注入 ===
                        if rounds == 5 and "suggestions" in reflection_data and reflection_data["suggestions"]:
                            suggestions_text = "\n".join([f"- {s}" for s in reflection_data["suggestions"]])
                            suggestion_message = {
                                "role": "assistant",
                                "content": f"【反思建议】\n{suggestions_text}"
                            }
                            system_prompt = Config.SYSTEM_PROMPT_TEMPLATE.format(
                                current_subtask=instruction,
                                final_goal=original_instruction,
                                language="Chinese",
                                completed_subtasks="无")
                            messages = [{"role": "user", "content": system_prompt}]
                            messages.append(suggestion_message)

                else:
                    print(f"当前是第{rounds + 1}步，不进行反思，继续执行")
            
            # 如果任务完成，直接返回
            if task_completed:
                return None

            # 9. 检查是否需要反思和重新规划（达到最大轮数）
            if rounds == max_rounds - 1:  # 达到最大轮数
                print("\n=== 达到最大轮数，子任务执行失败，开始反思 ===")
                
                # 达到最大轮数后立即截图
                screenshot_now_path, _, _ = self.action_executor.screenshot(
                    0, task_logger=task_logger, description="Max rounds reached")
                if screenshot_now_path:
                    # 重命名截图为screenshot_now
                    import os
                    new_screenshot_path = "screenshot_now.jpg"
                    if os.path.exists(new_screenshot_path):
                        os.remove(new_screenshot_path)
                    os.rename(screenshot_now_path, new_screenshot_path)
                    print(f"达到最大轮数后截图保存为: {new_screenshot_path}")
                    
                    # 将当前截图添加到ui-tars-agent的截图文件列表
                    ui_tars_screenshot_files.append(new_screenshot_path)
                    ui_tars_action_count += 1
                    
                    # 使用最新的截图进行反思（达到最大轮数时不需要重复检测限制）
                    reflection_data = self.reflection_manager.reflect_on_execution(
                        original_instruction or instruction, instruction, messages, new_screenshot_path, 
                        completed_subtasks=completed_subtasks, all_subtasks=all_subtasks, task_logger=task_logger)
                else:
                    print("无法获取达到最大轮数后的截图，使用原截图进行反思")
                    reflection_data = self.reflection_manager.reflect_on_execution(
                        original_instruction or instruction, instruction, messages, screenshot_path, 
                        completed_subtasks=completed_subtasks, all_subtasks=all_subtasks, task_logger=task_logger)
                
                # 子任务执行失败，直接重新生成计划
                print("子任务执行失败，直接重新生成计划")
                new_subtasks = self.planning_manager.regenerate_plan(
                    original_instruction or instruction, reflection_data, completed_subtasks, 
                    new_screenshot_path, instruction, task_logger, task_knowledge)
                if new_subtasks:
                    print(f"重新生成了 {len(new_subtasks)} 个子任务")
                    return new_subtasks
                else:
                    print("重新生成计划失败")
                    return "FAILED"  # 返回特殊值表示失败

            # 控制对话长度
            if len(messages) > 10:
                messages = [messages[0]] + messages[-9:]

            time.sleep(2)  # 等待操作生效

        print(f"Reached max rounds ({max_rounds}), exit")
        return None

# 全局代理实例
mobile_agent = MobileAgent()

# 导出主要函数
def run_gui_task(instruction, model_type="qwen25vl", max_rounds=None, is_subtask=True, 
                original_instruction=None, completed_subtasks=None, all_subtasks=None, 
                task_logger=None, task_knowledge=None):
    """执行GUI任务的主函数"""
    return mobile_agent.run_gui_task(
        instruction=instruction,
        model_type=model_type,
        max_rounds=max_rounds,
        is_subtask=is_subtask,
        original_instruction=original_instruction,
        completed_subtasks=completed_subtasks,
        all_subtasks=all_subtasks,
        task_logger=task_logger,
        task_knowledge=task_knowledge
    )

def decompose_task_to_subtasks(user_instruction, task_logger=None):
    """任务分解主函数"""
    return planning_manager.decompose_task_to_subtasks(user_instruction, task_logger) 
