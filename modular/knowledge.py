"""
知识管理模块
"""

import json
import os
from typing import Dict, List, Any, Optional

class KnowledgeManager:
    """知识管理器"""
    
    def __init__(self, knowledge_file: str = "knowledge.json"):
        self.knowledge_file = knowledge_file
        self.data = None
        self.knowledge_base = {}
        self._load_knowledge()
    
    def _load_knowledge(self):
        """加载知识库"""
        try:
            if os.path.exists(self.knowledge_file):
                with open(self.knowledge_file, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                self.knowledge_base = self._extract_features(self.data)
                print("知识库加载完成")
            else:
                print(f"知识库文件 {self.knowledge_file} 不存在")
                self.data = {}
                self.knowledge_base = {}
        except Exception as e:
            print(f"加载知识库失败: {e}")
            self.data = {}
            self.knowledge_base = {}
    
    def _extract_features(self, node: Dict[str, Any], app_name: str = None, 
                         knowledge_base: Dict[str, List[str]] = None) -> Dict[str, List[str]]:
        """提取特征"""
        if knowledge_base is None:
            knowledge_base = {}

        # 如果当前节点是一个app级别的节点
        if node.get("type") == "app":
            app_name = node["name"].replace("app", "").strip()
            knowledge_base[app_name] = []

        # 如果当前节点是功能类型（feature），加入对应的app的功能列表
        if node.get("type") in ["feature", "page", "menu"]:
            if app_name:
                knowledge_base[app_name].append(node["name"])

        # 递归遍历子节点
        for child in node.get("children", []):
            self._extract_features(child, app_name, knowledge_base)

        return knowledge_base
    
    def _find_path_with_notes(self, node: Dict[str, Any], target: str, 
                             path: List[Dict[str, Any]] = None) -> Optional[List[Dict[str, Any]]]:
        """搜索功能，返回路径（包含 note）"""
        if path is None:
            path = []
        
        # 如果是菜单类型且名称为空，包含前两个子节点的名称
        if node.get("type") == "menu" and node["name"] == "":
            children_info = []
            if node.get("children"):
                children_names = [child["name"] for child in node["children"][:2]]
                children_info = children_names
            path.append({
                "name": node["name"],
                "type": node.get("type"),
                "note": node.get("note"),
                "children_names": children_info
            })
        else:
            path.append({
                "name": node["name"],
                "type": node.get("type"),
                "note": node.get("note")
            })
        
        if node["name"] == target:
            return path
        for child in node.get("children", []):
            result = self._find_path_with_notes(child, target, path.copy())
            if result:
                return result
        return None
    


    def _step_description(self, step: Dict[str, Any], index: int) -> str:
        """根据节点类型选择模板"""
        t = step["type"]
        name = step["name"]
        note = f"（注意：{step['note']}）" if step.get("note") else ""
        
        if index == 0 and t == "app":
            return f'{index+1}、从手机桌面打开"{name}"'
        elif t == "menu":
            if name != "":
                return f'{index+1}、在当前页中可以看到名称为"{name}"的菜单{note}'
            else:
                # 如果菜单名称为空，使用前两个子节点的名称
                children_names = step.get("children_names", [])
                if children_names:
                    children_text = "、".join(children_names)
                    return f'{index+1}、在当前页中可以看到一个菜单，包含了"{children_text}等项目"{note}'
                else:
                    return f'{index+1}、在当前页中可以看到一个菜单{note}'
        elif t == "page":
            return f'{index+1}、点击"{name}"进入新页面{note}'
        elif t == "feature":
            return f'{index+1}、点击功能"{name}"{note}'
        else:
            return f'{index+1}、点击"{name}"{note}'
    
    def _path_to_sentence(self, path: List[Dict[str, Any]]) -> str:
        """将路径转换为句子描述"""
        return "\n".join(self._step_description(step, i) for i, step in enumerate(path))
    
    def _get_general_knowledge(self, instruction: str) -> str:
        """获取通用知识"""
        general_knowledge = []
        
        # 通用操作知识
        general_knowledge.append("通用操作提示：")
        general_knowledge.append("1、该系统使用的是adb键盘，无法点击发送/回车等按钮，对于需要用到搜索框的任务请直接点击搜索框自带的搜索按键")
        general_knowledge.append("2、如果找不到目标应用，可以尝试点击手机主页下方的搜索栏搜索")
        general_knowledge.append("3、对于输入文本的任务，不要拆成单独的子任务，与它的前置条件任务合并成一个")
        general_knowledge.append("4、从屏幕右上角下滑较长距离可以唤起功能中心，有截图、开启省电模式、屏幕录制等功能，如果没看到功能可以向左滑动")
        return "\n".join(general_knowledge)

    def query_from_instruction(self, instruction: str) -> str:
        """根据指令查询相关知识"""
        # 获取通用知识
        general_knowledge = self._get_general_knowledge(instruction)
        
        # 遍历知识库中的应用和功能
        for app_name, features in self.knowledge_base.items():
            # 如果app_name在instruction中，继续检查功能
            if app_name in instruction:
                # 找到所有在instruction中的feature
                matched_features = [feature for feature in features if feature and feature in instruction]
                # 选择匹配长度最长的feature
                if matched_features:
                    best_feature = max(matched_features, key=len)
                    path = self._find_path_with_notes(self.data, best_feature)
                    if path:
                        specific_knowledge = self._path_to_sentence(path)
                        # 组合通用知识和具体路径
                        return f"{general_knowledge}\n\n具体操作步骤：\n{specific_knowledge}"
        
        # 如果没有找到具体路径，只返回通用知识
        return f"{general_knowledge}\n\n未找到匹配的具体操作步骤。"
    
    def get_task_knowledge(self, original_instruction: str) -> str:
        """根据任务指令获取相关知识"""
        return self.query_from_instruction(original_instruction)
    
    def get_knowledge_base(self) -> Dict[str, List[str]]:
        """获取知识库"""
        return self.knowledge_base
    
    def reload_knowledge(self):
        """重新加载知识库"""
        self._load_knowledge()

# 全局知识管理器实例
knowledge_manager = KnowledgeManager() 