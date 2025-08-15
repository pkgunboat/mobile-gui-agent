"""
模型管理模块
"""

from openai import OpenAI
from typing import Dict, List, Any, Optional

from .config import Config

class ModelManager:
    """模型管理器"""
    
    def __init__(self):
        self.config = Config.get_model_config()
        self._init_clients()
    
    def _init_clients(self):
        """初始化模型客户端"""
        from openai import OpenAI
        plan_cfg = Config.MODEL_CONFIGS.get("plan_agent")
        format_cfg = Config.MODEL_CONFIGS.get("format_agent")
        operate_cfg = Config.MODEL_CONFIGS.get("operate_agent")
        reflection_cfg = Config.MODEL_CONFIGS.get("reflection_agent")

        self.main_client = OpenAI(
            api_key=operate_cfg["api_key"],
            base_url=operate_cfg["base_url"]
        )
        self.format_client = OpenAI(
            api_key=format_cfg["api_key"],
            base_url=format_cfg["base_url"]
        )
        self.reflection_client = OpenAI(
            api_key=reflection_cfg["api_key"],
            base_url=reflection_cfg["base_url"]
        )
        self.plan_client = OpenAI(
            api_key=plan_cfg["api_key"],
            base_url=plan_cfg["base_url"]
        )
    
    def call_main_model(self, messages: List[Dict[str, Any]], temperature: float = 0.0, model_type = "simple") -> str:
        """调用主模型"""
        try:
            if model_type == "simple":
                response = self.main_client.chat.completions.create(
                    model=self.config["model_id"],
                    messages=messages,
                    temperature=temperature,
                    stream=False
                )
                return response.choices[0].message.content
            elif model_type == "sync":
                response = self.plan_client.chat.completions.create(
                    model=self.config["plan_model"],
                    messages=messages,
                    # temperature=temperature,
                    # stream=False
                )
                full_output = response.choices[0].message.content.strip()
                print("GPT-5 原始输出:\n", full_output)
                lines = full_output.splitlines()
                thought_line = ""
                action_line = ""
                for line in lines:
                    if line.startswith("Thought:"):
                        thought_line = line
                    elif line.startswith("Action:"):
                        action_line = line
                if not thought_line or not action_line:
                    raise ValueError("输出格式不正确，未找到 Thought 或 Action 行")
                if any(x in action_line for x in ["click", "long_press", "drag"]):
                    prefix = action_line.split("(")[0] + "("
                    skeleton = f"{thought_line}\n{prefix}"
                    print("保留骨架:\n", skeleton)
                    response = self.main_client.chat.completions.create(
                        model=self.config["model_id"],
                        messages=messages+[{"role": "assistant", "content": skeleton}],
                        temperature=temperature,
                        stream=False
                    )
                    coords = response.choices[0].message.content.strip()
                    print("coords:\n", coords)  # 例如 "345,678)"
                    final_action = f"{skeleton}{coords}"
                    return final_action
                else:
                    return response.choices[0].message.content
        except Exception as e:
            print(f"Main model call failed: {e}")
            raise
    
    def call_format_model(self, messages: List[Dict[str, Any]]) -> str:
        """调用格式更正模型"""
        try:
            response = self.format_client.chat.completions.create(
                model=self.config["format_model"],
                messages=messages
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Format model call failed: {e}")
            raise
    
    def call_reflection_model(self, messages: List[Dict[str, Any]]) -> str:
        """调用反思模型"""
        try:
            response = self.reflection_client.chat.completions.create(
                model=self.config["reflection_model"],
                messages=messages
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Reflection model call failed: {e}")
            raise
    
    def call_plan_model(self, messages: List[Dict[str, Any]]) -> str:
        """调用规划模型"""
        try:
            response = self.plan_client.chat.completions.create(
                model=self.config["plan_model"],
                messages=messages
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Plan model call failed: {e}")
            raise
    
    def get_model_config(self) -> Dict[str, Any]:
        """获取模型配置"""
        return self.config

# 全局模型管理器实例
model_manager = ModelManager() 
