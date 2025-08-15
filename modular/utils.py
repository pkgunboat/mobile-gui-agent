"""
工具函数模块
"""

import re
import ast
import math
import base64
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image
import requests
import time
import os

from .config import Config

def convert_point_to_coordinates(text: str, is_answer: bool = False) -> str:
    """转换坐标点格式"""
    pattern = r"<point>(\d+)\s+(\d+)</point>"

    def replace_match(match):
        x1, y1 = map(int, match.groups())
        x = (x1 + x1) // 2
        y = (y1 + y1) // 2
        if is_answer:
            return f"({x},{y})"
        return f"({x},{y})"

    text = re.sub(r"\[EOS\]", "", text)
    return re.sub(pattern, replace_match, text).strip()

def parse_action(action_str: str) -> Optional[Dict[str, Any]]:
    """解析动作字符串"""
    try:
        node = ast.parse(action_str, mode='eval')
        if not isinstance(node, ast.Expression):
            raise ValueError("Not an expression")
        call = node.body
        if not isinstance(call, ast.Call):
            raise ValueError("Not a function call")

        if isinstance(call.func, ast.Name):
            func_name = call.func.id
        elif isinstance(call.func, ast.Attribute):
            func_name = call.func.attr
        else:
            func_name = None

        kwargs = {}
        for kw in call.keywords:
            key = kw.arg
            if isinstance(kw.value, ast.Constant):
                value = kw.value.value
            elif isinstance(kw.value, ast.Str):
                value = kw.value.s
            else:
                value = None
            kwargs[key] = value
        return {'function': func_name, 'args': kwargs}
    except Exception as e:
        print(f"Parse action failed: {e}")
        return None

def round_by_factor(number: int, factor: int) -> int:
    """按因子四舍五入"""
    return round(number / factor) * factor

def ceil_by_factor(number: int, factor: int) -> int:
    """按因子向上取整"""
    return math.ceil(number / factor) * factor

def floor_by_factor(number: int, factor: int) -> int:
    """按因子向下取整"""
    return math.floor(number / factor) * factor

def smart_resize(height: int, width: int, factor: int = None, 
                min_pixels: int = None, max_pixels: int = None, 
                max_ratio: int = None) -> Tuple[int, int]:
    """智能调整图像尺寸"""
    if factor is None:
        factor = Config.IMAGE_FACTOR
    if min_pixels is None:
        min_pixels = Config.MIN_PIXELS
    if max_pixels is None:
        max_pixels = Config.MAX_PIXELS
    if max_ratio is None:
        max_ratio = Config.MAX_RATIO
    
    if max(height, width) / min(height, width) > max_ratio:
        raise ValueError(f"Aspect ratio exceeds {max_ratio}")
    
    h_bar = max(factor, round_by_factor(height, factor))
    w_bar = max(factor, round_by_factor(width, factor))
    
    if h_bar * w_bar > max_pixels:
        beta = math.sqrt((height * width) / max_pixels)
        h_bar = floor_by_factor(height / beta, factor)
        w_bar = floor_by_factor(width / beta, factor)
    elif h_bar * w_bar < min_pixels:
        beta = math.sqrt(min_pixels / (height * width))
        h_bar = ceil_by_factor(height * beta, factor)
        w_bar = ceil_by_factor(width * beta, factor)
    
    return h_bar, w_bar

def parse_action_to_structure_output(text: str, factor: int, origin_h: int, 
                                   origin_w: int, model_type: str = "qwen25vl") -> List[Dict[str, Any]]:
    """解析动作输出为结构化格式"""
    text = text.strip()
    
    # 检查是否以finished开头
    if text.strip().lower().startswith("finished"):
        try:
            if "(" in text and ")" in text:
                start_idx = text.find("(")
                end_idx = text.rfind(")")
                content = text[start_idx + 1:end_idx].strip()
                if content.startswith("'") and content.endswith("'"):
                    content = content[1:-1]
                elif content.startswith('"') and content.endswith('"'):
                    content = content[1:-1]
                
                return [{
                    "thought": "",
                    "action_type": "finished",
                    "action_inputs": {"content": content},
                    "raw_text": text
                }]
            else:
                return [{
                    "thought": "",
                    "action_type": "finished",
                    "action_inputs": {"content": ""},
                    "raw_text": text
                }]
        except Exception as e:
            print(f"Error parsing finished action: {e}")
            return [{
                "thought": "",
                "action_type": "finished",
                "action_inputs": {"content": ""},
                "raw_text": text
            }]
    
    if "<point>" in text:
        text = convert_point_to_coordinates(text)
    if "point=" in text:
        text = text.replace("point=", "start_box=")
    if "start_point=" in text:
        text = text.replace("start_point=", "start_box=")
    if "end_point=" in text:
        text = text.replace("end_point=", "end_box=")

    smart_h, smart_w = smart_resize(origin_h, origin_w, factor=factor)

    # 提取thought和action
    thought = None
    if "Thought:" in text:
        thought = text.split("Thought:")[-1].split("Action:")[0].strip()
    if "Action:" in text:
        action_str = text.split("Action:")[-1].strip()
    else:
        # 没有Action，尝试直接解析
        thought = ""
        action_str = text
        try:
            parsed = parse_action(action_str)
            if not parsed:
                raise AssertionError("No Action found in response")
            func_name = parsed['function']
            args = parsed['args']
            action_inputs = {}
            for k, v in args.items():
                if k in ["start_box", "end_box", "start_point", "end_point"]:
                    if isinstance(v, str) and v.startswith("("):
                        v = v.replace("(", "").replace(")", "")
                        nums = list(map(float, v.split(",")))
                        if len(nums) == 2:
                            nums = [nums[0], nums[1], nums[0], nums[1]]
                        if model_type == "qwen25vl":
                            scaled = [
                                nums[0] * smart_w / 1000,
                                nums[1] * smart_h / 1000,
                                nums[2] * smart_w / 1000,
                                nums[3] * smart_h / 1000
                            ]
                        else:
                            scaled = [n * factor for n in nums]
                        if k in ["start_point", "start_box"]:
                            action_inputs["start_box"] = scaled
                        elif k in ["end_point", "end_box"]:
                            action_inputs["end_box"] = scaled
                    else:
                        action_inputs[k] = v
                else:
                    action_inputs[k] = v
            return [{
                "thought": thought,
                "action_type": func_name,
                "action_inputs": action_inputs,
                "raw_text": text
            }]
        except Exception as e:
            return [{"error": str(e), "raw_text": text}]

    # 解析动作
    parsed_actions = []
    for act in action_str.split(")\n"):
        if not act.strip():
            continue
        if not act.endswith(")"):
            act += ")"
        parsed = parse_action(act)
        if not parsed:
            continue
        func_name = parsed['function']
        args = parsed['args']

        action_inputs = {}
        for k, v in args.items():
            if k in ["start_box", "end_box", "start_point", "end_point"]:
                if isinstance(v, str) and v.startswith("("):
                    v = v.replace("(", "").replace(")", "")
                    nums = list(map(float, v.split(",")))
                    if len(nums) == 2:
                        nums = [nums[0], nums[1], nums[0], nums[1]]
                    
                    if model_type == "qwen25vl":
                        scaled = [
                            nums[0] * smart_w / 1000,
                            nums[1] * smart_h / 1000,
                            nums[2] * smart_w / 1000,
                            nums[3] * smart_h / 1000
                        ]
                    else:
                        scaled = [n * factor for n in nums]
                    
                    if k in ["start_point", "start_box"]:
                        action_inputs["start_box"] = scaled
                    elif k in ["end_point", "end_box"]:
                        action_inputs["end_box"] = scaled
                else:
                    action_inputs[k] = v
            else:
                action_inputs[k] = v

        parsed_actions.append({
            "thought": thought,
            "action_type": func_name,
            "action_inputs": action_inputs,
            "raw_text": text
        })
    return parsed_actions

def calculate_image_similarity(img1_path: str, img2_path: str) -> float:
    """计算两张图片的相似度"""
    try:
        import numpy as np
        
        img1 = Image.open(img1_path).convert('RGB')
        img2 = Image.open(img2_path).convert('RGB')
        
        size = (100, 100)
        img1 = img1.resize(size)
        img2 = img2.resize(size)
        
        img1_array = np.array(img1)
        img2_array = np.array(img2)
        
        diff = np.abs(img1_array - img2_array)
        similarity = 1 - (np.mean(diff) / 255.0)
        
        return similarity
    except Exception as e:
        print(f"图片相似度计算失败: {e}")
        return 0.0

def check_screenshot_service_health() -> bool:
    """检查截图服务健康状态"""
    try:
        r = requests.get(f"{Config.BASE_URL}/ping", timeout=5)
        if r.status_code != 200:
            print("Ping failed, service may be down")
            return False
        
        r = requests.get(f"{Config.BASE_URL}/screenshot", timeout=10)
        if r.status_code == 200 and len(r.content) > 0:
            print("Screenshot service is healthy")
            return True
        else:
            print(f"Screenshot service unhealthy: status={r.status_code}, content_length={len(r.content)}")
            return False
            
    except Exception as e:
        print(f"Health check failed: {e}")
        return False 