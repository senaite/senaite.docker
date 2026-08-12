# -*- coding: utf-8 -*-
"""
超简单的测试接收器 - 用于调试
"""
from flask import Flask, request, jsonify
from datetime import datetime
import json

app = Flask(__name__)


@app.route('/', methods=['GET'])
def index():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Simple Test Receiver</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
            h1 { color: #333; border-bottom: 2px solid #007bff; padding-bottom: 10px; }
            .success { background: #d4edda; padding: 15px; border-radius: 4px; margin: 10px 0; }
            form { background: #f5f5f5; padding: 20px; border-radius: 4px; margin: 20px 0; }
            textarea { width: 100%; height: 150px; font-family: monospace; }
            button { background: #007bff; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; }
            button:hover { background: #0056b3; }
            pre { background: #f8f9fa; padding: 10px; border-radius: 4px; }
        </style>
    </head>
    <body>
        <h1>🔬 Simple Test Receiver</h1>
        <div class="success">✓ Server is running!</div>
        <p>Endpoint: <code>POST /receive</code> or <code>GET /receive</code></p>
        
        <h2>Test Form</h2>
        <form id="testForm">
            <label>Test data (JSON):</label><br>
            <textarea id="testData">{"test": "value", "timestamp": "2024-01-01T12:00:00"}</textarea><br><br>
            <button type="button" onclick="sendTest()">Send Test</button>
        </form>
        
        <h2>Response:</h2>
        <pre id="response">Waiting for test...</pre>
        
        <h2>curl test command:</h2>
        <pre>curl -X POST -H "Content-Type: application/json" -d '{"test":"value"}' http://192.168.1.18:5001/receive</pre>
        
        <script>
            function sendTest() {
                var data = document.getElementById('testData').value;
                fetch('/receive', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: data
                })
                .then(response => response.text())
                .then(data => {
                    document.getElementById('response').textContent = data;
                })
                .catch(error => {
                    document.getElementById('response').textContent = 'Error: ' + error;
                });
            }
        </script>
    </body>
    </html>
    """


@app.route('/receive', methods=['POST', 'PUT', 'GET'])
def receive():
    print("=" * 60)
    print("[%s] Request received!" % datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print("  Method: %s" % request.method)
    print("  Content-Type: %s" % request.headers.get('Content-Type'))
    
    try:
        # 处理请求体 - Python 2.7 编码兼容
        request_body = request.data
        if request_body:
            # 尝试用 UTF-8 解码
            try:
                request_body_str = request_body.decode('utf-8')
            except UnicodeDecodeError:
                # 如果 UTF-8 失败，尝试用 latin-1
                request_body_str = request_body.decode('latin-1')
            print("  Request body: %s" % request_body_str)
        else:
            request_body_str = ""
            print("  No request body")
        
        # 解析 JSON
        data = {}
        if request_body_str:
            try:
                data = json.loads(request_body_str)
                print("  Parsed JSON: %s" % data)
            except Exception as e:
                print("  JSON parse error: %s" % e)
                data = {"raw_body": request_body_str}
    except Exception as e:
        print("  Request processing error: %s" % str(e))
        import traceback
        traceback.print_exc()
        data = {}
    
    # 构建响应 - 确保中文兼容
    response = {
        'success': True,
        'message': 'Received!',
        'received_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'data_received': data
    }
    
    print("  Response: %s" % json.dumps(response))
    print("=" * 60)
    
    return jsonify(response)


if __name__ == '__main__':
    print("=" * 60)
    print("Simple Test Receiver")
    print("=" * 60)
    print("Listening: http://0.0.0.0:5001")
    print("Endpoint: http://0.0.0.0:5001/receive")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5001, debug=True)
