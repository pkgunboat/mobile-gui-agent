#!/usr/bin/env python3
"""
模块化版本的Mobile Agent主入口文件
"""

import sys
import os
import time
from datetime import datetime

# 添加modular目录到Python路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'modular'))

from modular import (
    Config, TaskLogger, KnowledgeManager, ActionExecutor, 
    ReflectionManager, PlanningManager, MobileAgent,
    run_gui_task, decompose_task_to_subtasks
)

def main():
    """主函数"""
    print("=== Mobile Agent 模块化版本 ===")
    
    # 简单检查服务是否可用
    action_executor = ActionExecutor()
    if not action_executor.check_service_health():
        print("Warning: Screenshot service may not be ready")
        print("Will attempt to use retry mechanism during execution")
    
    original_instruction = "打开中国联通，打开腾讯视频VIP月卡+10G定向流量的权益界面"
    # 初始化任务日志记录器
    task_logger = TaskLogger(original_instruction)
    task_logger.logger.info(f"Starting task: {original_instruction}")
    
    # 任务分解并获取task_knowledge
    subtask_list = decompose_task_to_subtasks(user_instruction=original_instruction, task_logger=task_logger)
    print(subtask_list)
    
    # 获取已记录的任务知识
    task_knowledge = task_logger.get_task_knowledge()
    print(f"Task knowledge loaded: {len(task_knowledge)} characters")
    
    max_regeneration_cycles = Config.MAX_REGENERATION_CYCLES
    regeneration_cycle = 0
    completed_subtasks = []  # 跟踪已完成的子任务
    failed_subtasks = []  # 跟踪失败的子任务
    actual_completed_subtasks = []  # 跟踪实际完成的子任务列表
    
    while regeneration_cycle < max_regeneration_cycles:
        if not subtask_list:
            print("没有可执行的子任务，退出")
            break
            
        print(f"\n=== 执行计划 (第 {regeneration_cycle + 1} 轮) ===")
        if regeneration_cycle > 0:
            print(f"这是第 {regeneration_cycle} 次重新规划后的计划")
        
        print("\n子任务列表：")
        for task in subtask_list:
            print(f"子任务 {task['subtask_id']}：{task['description']}")
        
        # 执行所有子任务
        for i, task in enumerate(subtask_list):
            print(f"\n执行子任务 {task['subtask_id']}：{task['description']}")
            
            # 执行子任务
            subtask_start_time = time.time()
            result = run_gui_task(
                instruction=task['description'], 
                original_instruction=original_instruction,
                is_subtask=True,
                completed_subtasks=completed_subtasks,
                all_subtasks=subtask_list,
                task_logger=task_logger,
                task_knowledge=task_knowledge
            )
            subtask_execution_time = time.time() - subtask_start_time
            
            # 检查是否需要重新规划
            if isinstance(result, list) and len(result) > 0:
                print(f"检测到重新生成的子任务，开始第 {regeneration_cycle + 1} 次重新规划...")
                # 记录当前已完成的任务
                completed_subtasks.extend([t['description'] for t in subtask_list[:i]])
                # 记录失败的任务
                failed_subtasks.append(task['description'])
                subtask_list = result  # 更新子任务列表
                regeneration_cycle += 1
                break  # 跳出子任务循环，开始新的规划周期
            elif result is None:
                print("子任务执行完成")
                # 记录已完成的任务
                completed_subtasks.append(task['description'])
                actual_completed_subtasks.append(task['description'])
                # 记录子任务完成
                task_logger.log_subtask_completion(
                    subtask_id=task['subtask_id'],
                    subtask_description=task['description'],
                    completion_time=subtask_execution_time,
                    success=True
                )
                # 继续执行下一个子任务
                continue
            elif result == "FAILED":
                print("子任务执行失败，重新生成计划也失败")
                # 记录当前已完成的任务
                completed_subtasks.extend([t['description'] for t in subtask_list[:i]])
                # 记录失败的任务
                failed_subtasks.append(task['description'])
                # 记录子任务失败
                task_logger.log_subtask_completion(
                    subtask_id=task['subtask_id'],
                    subtask_description=task['description'],
                    completion_time=subtask_execution_time,
                    success=False
                )
                # 获取当前截图进行重新规划
                screenshot_path, _, _ = action_executor.screenshot(0, task_logger=task_logger, description="Subtask failed")
                if screenshot_path:
                    # 重命名截图为screenshot_now
                    import os
                    new_screenshot_path = "screenshot_now.jpg"
                    if os.path.exists(new_screenshot_path):
                        os.remove(new_screenshot_path)
                    os.rename(screenshot_path, new_screenshot_path)
                    print(f"子任务失败后截图保存为: {new_screenshot_path}")
                    
                    # 创建反思数据
                    reflection_data = {
                        "subtask_completed": False,
                        "current_issues": ["子任务执行失败"],
                        "suggestions": ["重新规划任务"],
                        "reflection_summary": "子任务执行失败，需要重新规划",
                        "need_replanning": True,
                        "replanning_reason": "子任务执行失败"
                    }
                    
                    # 重新生成计划
                    from modular import planning_manager
                    new_subtasks = planning_manager.regenerate_plan(
                        original_instruction, reflection_data, completed_subtasks, 
                        new_screenshot_path, task['description'], task_logger, task_knowledge)
                    if new_subtasks:
                        print(f"重新生成了 {len(new_subtasks)} 个子任务")
                        subtask_list = new_subtasks
                        regeneration_cycle += 1
                        break  # 跳出子任务循环，开始新的规划周期
                    else:
                        print("重新生成计划失败")
                        break
                else:
                    print("无法获取截图，退出")
                    break
        else:
            # 如果所有子任务都执行完成且没有触发重新规划，则检查总任务是否完成
            print("所有子任务执行完成，检查总任务是否完成")
            
            # 仅当子任务列表长度为1时进行最后的任务完成反思
            if len(subtask_list) == 1:
                print("子任务列表长度为1，进行最后的任务完成反思")
                
                # 获取当前截图
                screenshot_path, origin_w, origin_h = action_executor.screenshot(0, task_logger=task_logger, description="Total task completion check")
                if screenshot_path:
                    # 重命名截图为screenshot_now
                    import os
                    new_screenshot_path = "screenshot_now.jpg"
                    if os.path.exists(new_screenshot_path):
                        os.remove(new_screenshot_path)
                    os.rename(screenshot_path, new_screenshot_path)
                    print(f"总任务完成检查截图保存为: {new_screenshot_path}")
                    # 使用reflection agent判断总任务完成状态
                    print("\n=== 检查总任务完成状态 ===")
                    print(f"用户指令: {original_instruction}")
                    print(f"已完成子任务: {completed_subtasks}")
                    
                    # 构建总任务完成检查的提示词
                    total_task_check_prompt = f"""
请检查用户的总任务是否已经完成。

## 用户的总任务指令
{original_instruction}

## 已完成的所有子任务
"""
                    
                    if completed_subtasks:
                        for i, subtask in enumerate(completed_subtasks, 1):
                            total_task_check_prompt += f"{i}. {subtask}\n"
                    else:
                        total_task_check_prompt += "无已完成子任务\n"
                    
                    total_task_check_prompt += f"""
## 当前界面截图
[图片已提供]

请仔细分析：
1. 用户的总任务指令是什么？
2. 当前界面是否显示任务已经完成？
3. 所有必要的步骤是否都已经执行？
4. 是否有任何遗漏的步骤？

请以JSON格式返回：
{{
    "subtask_completed": true/false,
    "task_analysis": "详细的任务完成情况分析",
    "missing_steps": ["缺失的步骤1", "缺失的步骤2"],
    "completion_evidence": "证明任务完成的证据",
    "reflection_summary": "总任务完成情况总结"
}}
"""
                    
                    # 总任务完成检查基于所有保存的截图
                    from modular import reflection_manager
                    reflection_data = reflection_manager.check_total_task_completion_with_all_screenshots(
                        original_instruction, total_task_check_prompt, completed_subtasks, subtask_list, task_logger)
                    
                    if reflection_data.get("subtask_completed", False):
                        print("总任务已完成！")
                        if "task_analysis" in reflection_data:
                            print(f"任务分析: {reflection_data['task_analysis']}")
                        if "completion_evidence" in reflection_data:
                            print(f"完成证据: {reflection_data['completion_evidence']}")
                        if "reflection_summary" in reflection_data:
                            print(f"总结: {reflection_data['reflection_summary']}")
                        break
                    else:
                        print("总任务未完成，需要重新规划")
                        if "task_analysis" in reflection_data:
                            print(f"任务分析: {reflection_data['task_analysis']}")
                        if "missing_steps" in reflection_data:
                            print(f"缺失步骤: {reflection_data['missing_steps']}")
                        if "reflection_summary" in reflection_data:
                            print(f"总结: {reflection_data['reflection_summary']}")
                        
                        # 记录当前已完成的任务
                        completed_subtasks.extend([t['description'] for t in subtask_list])
                        # 重新生成计划
                        from modular import planning_manager
                        new_subtasks = planning_manager.regenerate_plan(
                            original_instruction, reflection_data, completed_subtasks, 
                            new_screenshot_path, task_logger=task_logger, task_knowledge=task_knowledge)
                        if new_subtasks:
                            print(f"重新生成了 {len(new_subtasks)} 个子任务")
                            subtask_list = new_subtasks
                            regeneration_cycle += 1
                            continue
                        else:
                            print("重新生成计划失败")
                            break
                else:
                    print("无法获取截图，假设任务完成")
                    break
            else:
                print(f"子任务列表长度为{len(subtask_list)}，跳过最后的任务完成反思")
                break
    
    # 记录任务完成状态
    if regeneration_cycle >= max_regeneration_cycles:
        final_status = "MAX_REGENERATION_CYCLES_REACHED"
        print(f"达到最大重新规划次数 ({max_regeneration_cycles})，任务执行结束")
    else:
        final_status = "COMPLETED"
        print("任务执行完成")
    
    # 记录任务完成
    task_logger.log_task_completion(final_status, actual_completed_subtasks, failed_subtasks)
    
    # 保存日志
    task_logger.save_log()
    
    # 打印任务摘要
    summary = task_logger.get_summary()
    print("\n=== 任务执行摘要 ===")
    print(f"任务名称: {summary['task_name']}")
    print(f"任务文件夹: {summary['task_folder']}")
    print(f"总运行时间: {summary['total_runtime']:.2f}秒")
    print(f"总模型调用次数: {summary['total_model_calls']}")
    print(f"总动作执行次数: {summary['total_actions']}")
    print(f"总反思次数: {summary['total_reflections']}")
    print(f"总计划重新生成次数: {summary['total_plan_regenerations']}")
    print(f"总错误次数: {summary['total_errors']}")
    print(f"总截图数量: {summary['total_screenshots']}")
    print(f"最终状态: {summary['final_status']}")
    
    print("\n=== 模型执行时间统计 ===")
    for model, exec_time in summary['model_execution_times'].items():
        print(f"{model}: {exec_time:.2f}秒")
    
    # 打印实际完成的子任务列表
    print("\n=== 实际完成的子任务列表 ===")
    if actual_completed_subtasks:
        for i, subtask in enumerate(actual_completed_subtasks, 1):
            print(f"{i}. {subtask}")
        print(f"\n总共完成了 {len(actual_completed_subtasks)} 个子任务")
    else:
        print("没有完成任何子任务")

if __name__ == "__main__":
    main() 