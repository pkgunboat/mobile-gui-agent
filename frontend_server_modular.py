from flask import Flask, request, jsonify, Response, send_file
from flask_cors import CORS
import json
import time
import threading
import queue
import os
import sys
from datetime import datetime
import logging
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.append(str(project_root))

# 导入模块化的Mobile Agent
from modular import run_gui_task, decompose_task_to_subtasks, TaskLogger

app = Flask(__name__)
CORS(app)  # 启用跨域支持

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 全局变量
current_task = None
task_queue = queue.Queue()
execution_status = {
    'is_running': False,
    'current_task': None,
    'progress': {'current': 0, 'total': 0},
    'status': 'idle'
}

class TaskExecutor:
    def __init__(self):
        self.current_task_logger = None
        self.should_stop = False
        self.task_knowledge = None
        
    def execute_task(self, instruction):
        """执行任务的主要方法"""
        global execution_status
        
        try:
            execution_status['is_running'] = True
            execution_status['current_task'] = instruction
            execution_status['status'] = 'starting'
            
            # 创建任务日志记录器
            self.current_task_logger = TaskLogger(instruction)
            
            # 任务分解
            execution_status['status'] = 'decomposing'
            yield json.dumps({
                'type': 'log',
                'message': '开始任务分解...',
                'level': 'info'
            }) + '\n'
            
            subtask_list = decompose_task_to_subtasks(
                user_instruction=instruction, 
                task_logger=self.current_task_logger
            )
            
            if not subtask_list:
                yield json.dumps({
                    'type': 'log',
                    'message': '任务分解失败，无法生成子任务',
                    'level': 'error'
                }) + '\n'
                return
            
            # 获取已记录的任务知识
            self.task_knowledge = self.current_task_logger.get_task_knowledge()
            yield json.dumps({
                'type': 'log',
                'message': f'任务知识已获取: {len(self.task_knowledge)} 字符',
                'level': 'info'
            }) + '\n'
            
            execution_status['progress']['total'] = len(subtask_list)
            execution_status['progress']['current'] = 0
            
            yield json.dumps({
                'type': 'log',
                'message': f'任务分解完成，共生成 {len(subtask_list)} 个子任务',
                'level': 'info'
            }) + '\n'
            
            yield json.dumps({
                'type': 'subtask',
                'current': 0,
                'total': len(subtask_list)
            }) + '\n'
            
            # 执行子任务
            max_regeneration_cycles = 10
            regeneration_cycle = 0
            completed_subtasks = []
            failed_subtasks = []
            actual_completed_subtasks = []
            
            while regeneration_cycle < max_regeneration_cycles and not self.should_stop:
                if not subtask_list:
                    yield json.dumps({
                        'type': 'log',
                        'message': '没有可执行的子任务，退出',
                        'level': 'warning'
                    }) + '\n'
                    break
                
                yield json.dumps({
                    'type': 'log',
                    'message': f'开始第 {regeneration_cycle + 1} 轮执行，剩余 {len(subtask_list)} 个子任务',
                    'level': 'info'
                }) + '\n'
                
                # 执行当前子任务列表
                for i, subtask in enumerate(subtask_list):
                    if self.should_stop:
                        break
                    
                    execution_status['progress']['current'] = i + 1
                    execution_status['status'] = 'executing'
                    
                    yield json.dumps({
                        'type': 'log',
                        'message': f'执行子任务 {i + 1}/{len(subtask_list)}: {subtask.get("description", "未知任务")}',
                        'level': 'info'
                    }) + '\n'
                    
                    yield json.dumps({
                        'type': 'progress',
                        'current': i + 1,
                        'total': len(subtask_list)
                    }) + '\n'
                    
                    # 执行子任务
                    result = run_gui_task(
                        instruction=subtask.get("description", ""),
                        model_type="qwen25vl",
                        max_rounds=10,
                        is_subtask=True,
                        original_instruction=instruction,
                        completed_subtasks=completed_subtasks,
                        all_subtasks=subtask_list,
                        task_logger=self.current_task_logger,
                        task_knowledge=self.task_knowledge
                    )
                    
                    # 发送截图更新
                    yield json.dumps({
                        'type': 'screenshot',
                        'path': 'screenshot_now.jpg',
                        'timestamp': datetime.now().isoformat()
                    }) + '\n'
                    
                    if result is None:
                        # 子任务成功完成
                        completed_subtasks.append(subtask.get("description", ""))
                        actual_completed_subtasks.append(subtask)
                        yield json.dumps({
                            'type': 'log',
                            'message': f'子任务 {i + 1} 执行成功',
                            'level': 'success'
                        }) + '\n'
                    elif result == "FAILED":
                        # 子任务执行失败
                        failed_subtasks.append(subtask)
                        yield json.dumps({
                            'type': 'log',
                            'message': f'子任务 {i + 1} 执行失败',
                            'level': 'error'
                        }) + '\n'
                    elif isinstance(result, list):
                        # 需要重新规划
                        yield json.dumps({
                            'type': 'log',
                            'message': f'子任务 {i + 1} 需要重新规划，生成 {len(result)} 个新子任务',
                            'level': 'warning'
                        }) + '\n'
                        subtask_list = result
                        break
                    else:
                        # 其他情况
                        yield json.dumps({
                            'type': 'log',
                            'message': f'子任务 {i + 1} 执行结果异常: {result}',
                            'level': 'error'
                        }) + '\n'
                        failed_subtasks.append(subtask)
                
                regeneration_cycle += 1
                
                if self.should_stop:
                    break
            
            # 任务完成
            execution_status['status'] = 'completed'
            yield json.dumps({
                'type': 'log',
                'message': f'任务执行完成。成功: {len(actual_completed_subtasks)}, 失败: {len(failed_subtasks)}',
                'level': 'info'
            }) + '\n'
            
            yield json.dumps({
                'type': 'completion',
                'completed': len(actual_completed_subtasks),
                'failed': len(failed_subtasks),
                'total': len(actual_completed_subtasks) + len(failed_subtasks)
            }) + '\n'
            
        except Exception as e:
            execution_status['status'] = 'error'
            yield json.dumps({
                'type': 'log',
                'message': f'任务执行出错: {str(e)}',
                'level': 'error'
            }) + '\n'
        finally:
            execution_status['is_running'] = False
            execution_status['current_task'] = None
            self.should_stop = False  # 重置停止标志

# 全局任务执行器
task_executor = TaskExecutor()

@app.route('/')
def index():
    """前端页面"""
    return send_file('frontend/index.html')

@app.route('/script.js')
def script():
    """JavaScript文件"""
    return send_file('frontend/script.js')

@app.route('/favicon.ico')
def favicon():
    """网站图标"""
    return '', 204  # 返回空内容，避免404错误

@app.route('/ping')
def ping():
    """健康检查"""
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})

@app.route('/execute_task', methods=['POST'])
def execute_task():
    """执行任务"""
    global task_executor
    
    if execution_status['is_running']:
        return jsonify({'error': '任务正在执行中'}), 400
    
    data = request.get_json()
    instruction = data.get('instruction', '').strip()
    
    if not instruction:
        return jsonify({'error': '任务指令不能为空'}), 400
    
    def generate():
        for chunk in task_executor.execute_task(instruction):
            yield chunk
    
    return Response(generate(), mimetype='text/plain')

@app.route('/stop_task', methods=['POST'])
def stop_task():
    """停止任务"""
    global task_executor
    
    if not execution_status['is_running']:
        return jsonify({'message': '没有正在执行的任务'})
    
    task_executor.should_stop = True
    execution_status['status'] = 'stopping'
    execution_status['is_running'] = False  # 立即标记为停止状态
    
    return jsonify({'message': '正在停止任务...'})

@app.route('/status')
def get_status():
    """获取执行状态"""
    return jsonify(execution_status)

@app.route('/screenshot')
def get_screenshot():
    """获取当前截图"""
    try:
        screenshot_path = "screenshot_now.jpg"
        if os.path.exists(screenshot_path):
            return send_file(screenshot_path, mimetype='image/jpeg')
        else:
            return jsonify({'error': '截图文件不存在'}), 404
    except Exception as e:
        return jsonify({'error': f'获取截图失败: {str(e)}'}), 500

@app.route('/logs')
def get_logs():
    """获取日志"""
    try:
        if task_executor.current_task_logger:
            logs = task_executor.current_task_logger.get_logs()
            return jsonify({'logs': logs})
        else:
            return jsonify({'logs': []})
    except Exception as e:
        return jsonify({'error': f'获取日志失败: {str(e)}'}), 500

@app.route('/stats')
def get_stats():
    """获取统计信息"""
    try:
        if task_executor.current_task_logger:
            stats = task_executor.current_task_logger.get_stats()
            return jsonify(stats)
        else:
            return jsonify({
                'total_actions': 0,
                'model_calls': 0,
                'execution_time': 0,
                'success_rate': 0
            })
    except Exception as e:
        return jsonify({'error': f'获取统计信息失败: {str(e)}'}), 500

if __name__ == '__main__':
    print("=== Mobile Agent 模块化前端服务器 ===")
    print("访问地址: http://localhost:50006")
    print("按 Ctrl+C 停止服务器")
    print()
    
    app.run(host='0.0.0.0', port=50006, debug=False, threaded=True) 