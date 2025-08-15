"""
日志管理模块
"""

import os
import json
import time
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

from .config import Config

class TaskLogger:
    """任务日志记录器"""
    
    def __init__(self, task_name: str):
        """初始化任务日志记录器"""
        self.task_name = task_name
        self.start_time = time.time()
        self.log_data = {
            "task_name": task_name,
            "start_time": datetime.now().isoformat(),
            "model_calls": [],
            "actions_executed": [],
            "reflections": [],
            "plan_regenerations": [],
            "errors": [],
            "total_runtime": 0,
            "task_knowledge": None
        }
        
        # 创建任务文件夹
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.task_folder = f"task_{task_name[:10]}_{timestamp}"

        os.makedirs(self.task_folder, exist_ok=True)
        
        # 创建日志文件
        self.log_filename = os.path.join(self.task_folder, f"task_log_{task_name}_{timestamp}.json")
        
        # 设置控制台日志
        logging.basicConfig(
            level=getattr(logging, Config.LOG_LEVEL),
            format=Config.LOG_FORMAT,
            handlers=[
                logging.FileHandler(os.path.join(self.task_folder, f"task_log_{task_name[:10]}_{timestamp}.txt")),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # 截图计数器
        self.screenshot_counter = 0
        self.screenshots = []
        
    def log_model_call(self, model_name: str, call_type: str, input_data: Dict, output_data: Dict, 
                      execution_time: float, success: bool = True, error: str = None):
        """记录模型调用"""
        model_call = {
            "timestamp": datetime.now().isoformat(),
            "model_name": model_name,
            "call_type": call_type,  # "ui_tars", "format", "reflection", "plan", "decompose"
            "input_data": input_data,
            "output_data": output_data,
            "execution_time": execution_time,
            "success": success,
            "error": error
        }
        self.log_data["model_calls"].append(model_call)
        self.logger.info(f"Model call: {model_name} ({call_type}) - {execution_time:.2f}s - {'Success' if success else 'Failed'}")
        
    def log_action_execution(self, action_type: str, action_inputs: Dict, thought: str, 
                           execution_time: float, success: bool = True, error: str = None):
        """记录动作执行"""
        action = {
            "timestamp": datetime.now().isoformat(),
            "action_type": action_type,
            "action_inputs": action_inputs,
            "thought": thought,
            "execution_time": execution_time,
            "success": success,
            "error": error
        }
        self.log_data["actions_executed"].append(action)
        self.logger.info(f"Action: {action_type} - {execution_time:.2f}s - {'Success' if success else 'Failed'}")
        
    def log_reflection(self, reflection_data: Dict, execution_time: float):
        """记录反思过程"""
        reflection = {
            "timestamp": datetime.now().isoformat(),
            "reflection_data": reflection_data,
            "execution_time": execution_time
        }
        self.log_data["reflections"].append(reflection)
        self.logger.info(f"Reflection completed - {execution_time:.2f}s")
        
    def log_plan_regeneration(self, old_plan: List, new_plan: List, reason: str, execution_time: float):
        """记录计划重新生成"""
        plan_regen = {
            "timestamp": datetime.now().isoformat(),
            "old_plan": old_plan,
            "new_plan": new_plan,
            "reason": reason,
            "execution_time": execution_time
        }
        self.log_data["plan_regenerations"].append(plan_regen)
        self.logger.info(f"Plan regeneration - {execution_time:.2f}s - {len(new_plan)} new subtasks")
        
    def log_task_knowledge(self, task_knowledge: str):
        """记录任务知识"""
        self.log_data["task_knowledge"] = task_knowledge
        self.logger.info(f"Task knowledge recorded: {len(task_knowledge)} characters")
        
    def get_task_knowledge(self) -> str:
        """获取任务知识"""
        return self.log_data.get("task_knowledge", "")
        
    def log_error(self, error_type: str, error_message: str, context: Dict = None):
        """记录错误"""
        error = {
            "timestamp": datetime.now().isoformat(),
            "error_type": error_type,
            "error_message": error_message,
            "context": context or {}
        }
        self.log_data["errors"].append(error)
        self.logger.error(f"Error ({error_type}): {error_message}")
        
    def log_subtask_completion(self, subtask_id: int, subtask_description: str, 
                             completion_time: float, success: bool):
        """记录子任务完成"""
        self.logger.info(f"Subtask {subtask_id} completed: {subtask_description} - {completion_time:.2f}s - {'Success' if success else 'Failed'}")
        
    def log_task_completion(self, final_status: str, completed_subtasks: List, failed_subtasks: List):
        """记录任务完成"""
        self.log_data["total_runtime"] = time.time() - self.start_time
        self.log_data["end_time"] = datetime.now().isoformat()
        self.log_data["final_status"] = final_status
        self.log_data["completed_subtasks"] = completed_subtasks
        self.log_data["failed_subtasks"] = failed_subtasks
        
        self.logger.info(f"Task completed: {final_status} - Total runtime: {self.log_data['total_runtime']:.2f}s")
        self.logger.info(f"Completed subtasks: {len(completed_subtasks)}, Failed subtasks: {len(failed_subtasks)}")
        
    def save_log(self):
        """保存日志到文件"""
        try:
            with open(self.log_filename, 'w', encoding='utf-8') as f:
                json.dump(self.log_data, f, ensure_ascii=False, indent=2)
            self.logger.info(f"Log saved to {self.log_filename}")
        except Exception as e:
            self.logger.error(f"Failed to save log: {e}")
            
    def save_screenshot(self, screenshot_path: str, description: str = "") -> str:
        """保存截图到任务文件夹"""
        if not os.path.exists(screenshot_path):
            self.logger.warning(f"Screenshot file not found: {screenshot_path}")
            return ""
        
        # 生成新的文件名
        self.screenshot_counter += 1
        timestamp = datetime.now().strftime("%H%M%S")
        new_filename = f"screenshot_{self.screenshot_counter:03d}_{timestamp}.jpg"
        new_path = os.path.join(self.task_folder, new_filename)
        
        try:
            # 复制截图到任务文件夹
            import shutil
            shutil.copy2(screenshot_path, new_path)
            
            # 记录截图信息
            screenshot_info = {
                "filename": new_filename,
                "original_path": screenshot_path,
                "description": description,
                "timestamp": datetime.now().isoformat(),
                "counter": self.screenshot_counter
            }
            self.screenshots.append(screenshot_info)
            
            self.logger.info(f"Screenshot saved: {new_filename} - {description}")
            return new_path
        except Exception as e:
            self.logger.error(f"Failed to save screenshot: {e}")
            return ""
    
    def get_all_screenshots(self) -> List[str]:
        """获取所有保存的截图路径"""
        return [os.path.join(self.task_folder, s["filename"]) for s in self.screenshots]
    
    def get_summary(self) -> Dict:
        """获取任务执行摘要"""
        total_model_calls = len(self.log_data["model_calls"])
        total_actions = len(self.log_data["actions_executed"])
        total_reflections = len(self.log_data["reflections"])
        total_plan_regens = len(self.log_data["plan_regenerations"])
        total_errors = len(self.log_data["errors"])
        
        # 计算各模型的总调用时间
        model_times = {}
        for call in self.log_data["model_calls"]:
            model = call["model_name"]
            if model not in model_times:
                model_times[model] = 0
            model_times[model] += call["execution_time"]
            
        return {
            "task_name": self.task_name,
            "total_runtime": self.log_data["total_runtime"],
            "total_model_calls": total_model_calls,
            "total_actions": total_actions,
            "total_reflections": total_reflections,
            "total_plan_regenerations": total_plan_regens,
            "total_errors": total_errors,
            "model_execution_times": model_times,
            "final_status": self.log_data.get("final_status", "Unknown"),
            "total_screenshots": len(self.screenshots),
            "task_folder": self.task_folder
        } 