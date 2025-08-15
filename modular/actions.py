"""
动作执行模块
"""

import time
import requests
from typing import Dict, Any, Optional, Tuple

from .config import Config
from .utils import check_screenshot_service_health

class ActionExecutor:
    """动作执行器"""
    
    def __init__(self):
        self.base_url = Config.BASE_URL
    
    def test_ping(self) -> Dict[str, Any]:
        """测试连接"""
        try:
            r = requests.get(f"{self.base_url}/ping")
            return r.json()
        except Exception as e:
            print(f"Ping failed: {e}")
            return {"error": str(e)}
    
    def tap(self, x: int, y: int) -> Dict[str, Any]:
        """点击操作"""
        try:
            r = requests.post(f"{self.base_url}/action", json={
                "type": "tap",
                "x": x,
                "y": y
            })
            result = r.json()
            print(f"Tap ({x},{y}): {result}")
            return result
        except Exception as e:
            print(f"Tap failed: {e}")
            return {"error": str(e)}
    
    def type_text(self, text: str) -> Dict[str, Any]:
        """输入文本"""
        try:
            r = requests.post(f"{self.base_url}/action", json={
                "type": "type",
                "text": text
            })
            result = r.json()
            print(f"Type '{text}': {result}")
            return result
        except Exception as e:
            print(f"Type failed: {e}")
            return {"error": str(e)}
    
    def slide(self, x1: int, y1: int, x2: int, y2: int) -> Dict[str, Any]:
        """滑动操作"""
        try:
            print(f"Attempting slide from ({x1},{y1}) to ({x2},{y2})")
            r = requests.post(f"{self.base_url}/action", json={
                "type": "slide",
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2
            }, timeout=10)
            
            if r.status_code == 200:
                result = r.json()
                print(f"Slide response: {result}")
                if result.get("status") == "success":
                    print("Slide executed successfully")
                else:
                    print(f"Slide failed: {result}")
                return result
            else:
                print(f"Slide request failed with status {r.status_code}: {r.text}")
                return {"error": f"HTTP {r.status_code}"}
                
        except requests.exceptions.RequestException as e:
            print(f"Slide request error: {e}")
            return {"error": str(e)}
        except Exception as e:
            print(f"Slide execution error: {e}")
            return {"error": str(e)}
    
    def back(self) -> Dict[str, Any]:
        """返回操作"""
        try:
            r = requests.post(f"{self.base_url}/action", json={"type": "back"})
            result = r.json()
            print(f"Back: {result}")
            return result
        except Exception as e:
            print(f"Back failed: {e}")
            return {"error": str(e)}
    
    def home(self) -> Dict[str, Any]:
        """主页操作"""
        try:
            r = requests.post(f"{self.base_url}/action", json={"type": "home"})
            result = r.json()
            print(f"Home: {result}")
            return result
        except Exception as e:
            print(f"Home failed: {e}")
            return {"error": str(e)}
    
    def screenshot(self, step: int = 0, max_retries: int = 3, 
                  task_logger=None, description: str = "") -> Tuple[Optional[str], int, int]:
        """获取截图"""
        for attempt in range(max_retries):
            try:
                print(f"Screenshot attempt {attempt + 1}/{max_retries}")
                r = requests.get(f"{self.base_url}/screenshot", timeout=10)
                
                if r.status_code == 200:
                    content_type = r.headers.get('content-type', '')
                    print(f"Response content-type: {content_type}")
                    
                    if len(r.content) == 0:
                        print("Empty response content")
                        if attempt < max_retries - 1:
                            time.sleep(2)
                            continue
                        else:
                            return None, 0, 0
                    
                    # 尝试保存为不同格式
                    possible_extensions = ['.jpg', '.jpeg', '.png']
                    screenshot_path = None
                    
                    for ext in possible_extensions:
                        temp_path = f"screenshot_{step}{ext}"
                        try:
                            with open(temp_path, "wb") as f:
                                f.write(r.content)
                            
                            # 验证图片是否可以打开
                            from PIL import Image
                            with Image.open(temp_path) as img:
                                width, height = img.size
                                print(f"Screenshot saved as {temp_path} (size: {width}x{height})")
                                screenshot_path = temp_path
                                break
                        except Exception as e:
                            print(f"Failed to save as {temp_path}: {e}")
                            # 删除损坏的文件
                            import os
                            if os.path.exists(temp_path):
                                os.remove(temp_path)
                            continue
                    
                    if screenshot_path:
                        # 如果提供了task_logger，保存截图到任务文件夹
                        if task_logger:
                            task_logger.save_screenshot(screenshot_path, description)
                        return screenshot_path, width, height
                    else:
                        print("Failed to save screenshot in any format")
                        if attempt < max_retries - 1:
                            time.sleep(2)
                            continue
                        else:
                            return None, 0, 0
                else:
                    print(f"Screenshot failed with status {r.status_code}: {r.text}")
                    if attempt < max_retries - 1:
                        time.sleep(2)
                        continue
                    else:
                        return None, 0, 0
                        
            except requests.exceptions.RequestException as e:
                print(f"Request error on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                else:
                    return None, 0, 0
            except Exception as e:
                print(f"Unexpected error on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                else:
                    return None, 0, 0
        
        print(f"All {max_retries} screenshot attempts failed")
        return None, 0, 0
    
    def check_service_health(self) -> bool:
        """检查服务健康状态"""
        return check_screenshot_service_health()
    
    def test_drag_functionality(self):
        """测试drag功能"""
        print("Testing drag functionality...")
        
        test_coordinates = [
            (100, 500, 100, 200),  # 垂直向上滑动
            (100, 200, 100, 500),  # 垂直向下滑动
            (100, 300, 300, 300),  # 水平向右滑动
            (300, 300, 100, 300),  # 水平向左滑动
        ]
        
        for i, (x1, y1, x2, y2) in enumerate(test_coordinates):
            print(f"\nTest {i+1}: Slide from ({x1},{y1}) to ({x2},{y2})")
            try:
                self.slide(x1, y1, x2, y2)
                time.sleep(1)
            except Exception as e:
                print(f"Test {i+1} failed: {e}")
        
        print("Drag functionality test completed")

# 全局动作执行器实例
action_executor = ActionExecutor() 