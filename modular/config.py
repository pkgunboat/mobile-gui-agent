"""
配置管理模块
"""

import os
from typing import Dict, Any

class Config:
    """配置管理类"""
    
    # 图像处理配置
    IMAGE_FACTOR = 28
    MIN_PIXELS = 100 * 28 * 28
    MAX_PIXELS = 16384 * 28 * 28
    MAX_RATIO = 200

    # API配置
    DEERAPI_KEY = 'xxx'
    DEERAPI_URL = 'https://api.deerapi.com/v1/'
    
    # 模型配置
    MODEL_ID = "doubao-1-5-ui-tars-250428"
    FORMAT_MODEL_NAME = "gpt-5-mini-2025-08-07"
    REFLECTION_MODEL_NAME = "gpt-5-2025-08-07"
    PLAN_MODEL_NAME = "gpt-5-2025-08-07"
    
    # API配置
    BASE_URL = "http://localhost:50005"
    LITELLM_BASE_URL = "https://litellm.mybigai.ac.cn/"

    # API Keys
    API_KEY = "xxx"
    LITELLM_API_KEY = "sk-xxx"
    FORMAT_API_KEY = DEERAPI_KEY
    REFLECTION_API_KEY = DEERAPI_KEY
    PLAN_API_KEY = DEERAPI_KEY
    
    # 系统提示词模板
    SYSTEM_PROMPT_TEMPLATE = '''
You are a GUI agent. You are given a subtask and your action history, with screenshots. You need to perform the next action to complete the current subtask. 

## Final Goal
{final_goal}

## Current Subtask
{current_subtask}

## Completed Subtasks
{completed_subtasks}

## Output Format
```
Thought: ...
Action: ...
```
1. 先思考过程，以"Thought:"开头
2. 再动作指令，以"Action:"开头，动作格式为函数调用

## Action Space
click(point='<point>x1 y1</point>')
type(content='') #If you want to submit your input, use "\\n" at the end of `content`.
drag(start_point='<point>x1 y1</point>', end_point='<point>x2 y2</point>')
long_press(point='<point>x1 y1</point>')
press_home()
press_back()
finished(content='xxx') # Use escape characters \\', \\", and \\n in content part to ensure we can parse the content in normal python string format.

## Note
- Use {language} in `Thought` part.
- Focus on completing the current subtask: {current_subtask}. The final goal and previously completed subtasks provide context for your current progress.
- Write a small plan and finally summarize your next action (with its target element) in one sentence in `Thought` part.
- Only use "finished()" when the current subtask is completed.
- Consider the completed subtasks to understand the current progress and avoid repeating completed actions.
'''
    
    # 任务执行配置
    MAX_ROUNDS = 10
    MAX_REGENERATION_CYCLES = 10
    
    # 日志配置
    LOG_LEVEL = "INFO"
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # 多模型/Agent配置
    MODEL_CONFIGS = {
        # 示例：
        # "main_agent": {"base_url": "http://localhost:50005", "api_key": "sk-xxx"},
        # "agent2": {"base_url": "https://api2.example.com", "api_key": "sk-yyy"},
        "plan_agent": {
            "base_url": LITELLM_BASE_URL,
            "api_key": LITELLM_API_KEY
        },
        "format_agent": {
            "base_url": LITELLM_BASE_URL,
            "api_key": LITELLM_API_KEY
        },
        "operate_agent": {
            "base_url": LITELLM_BASE_URL,
            "api_key": API_KEY
        },
        "reflection_agent": {
            "base_url": LITELLM_BASE_URL,
            "api_key": LITELLM_API_KEY
        },
        # 可继续添加其他agent/model
    }

    @classmethod
    def get_model_config(cls) -> Dict[str, Any]:
        """获取模型配置"""
        return {
            "model_id": cls.MODEL_ID,
            "format_model": cls.FORMAT_MODEL_NAME,
            "reflection_model": cls.REFLECTION_MODEL_NAME,
            "plan_model": cls.PLAN_MODEL_NAME,
            "base_url": cls.LITELLM_BASE_URL,
            "api_keys": {
                "main": cls.API_KEY,
                "format": cls.FORMAT_API_KEY,
                "reflection": cls.REFLECTION_API_KEY,
                "plan": cls.PLAN_API_KEY
            }
        }
    
    @classmethod
    def get_action_config(cls) -> Dict[str, Any]:
        """获取动作执行配置"""
        return {
            "base_url": cls.BASE_URL,
            "max_rounds": cls.MAX_ROUNDS,
            "max_regeneration_cycles": cls.MAX_REGENERATION_CYCLES
        }
    
    @classmethod
    def get_image_config(cls) -> Dict[str, Any]:
        """获取图像处理配置"""
        return {
            "factor": cls.IMAGE_FACTOR,
            "min_pixels": cls.MIN_PIXELS,
            "max_pixels": cls.MAX_PIXELS,
            "max_ratio": cls.MAX_RATIO
        } 

    @classmethod
    def get_model_api_config(cls, model_name: str) -> Dict[str, str]:
        """根据模型/Agent名获取base_url和api_key"""
        return cls.MODEL_CONFIGS.get(model_name, {
            "base_url": cls.LITELLM_BASE_URL,
            "api_key": cls.API_KEY
        }) 
