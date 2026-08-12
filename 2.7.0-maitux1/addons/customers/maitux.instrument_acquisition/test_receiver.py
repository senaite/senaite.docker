# -*- coding: utf-8 -*-
"""
仪器数据转发测试接收服务器
使用Flask搭建的简单HTTP服务器，用于接收和显示转发的仪器数据
"""

from flask import Flask, request, jsonify
from datetime import datetime
import json

app = Flask(__name__)

# 存储接收到的数据
received_data = []


@app.route('/', methods=['GET'])
def index():
    """主页 - 显示接收到的数据"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Instrument Data Forward Test Receiver</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
                background: #f5f5f5;
            }
            h1 {
                color: #333;
                border-bottom: 2px solid #007bff;
                padding-bottom: 10px;
            }
            .status {
                background: #d4edda;
                border: 1px solid #c3e6cb;
                padding: 15px;
                border-radius: 4px;
                margin-bottom: 20px;
            }
            .data-item {
                background: white;
                border: 1px solid #ddd;
                padding: 15px;
                margin-bottom: 15px;
                border-radius: 4px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .data-header {
                display: flex;
                justify-content: space-between;
                margin-bottom: 10px;
                padding-bottom: 10px;
                border-bottom: 1px solid #eee;
            }
            .timestamp {
                color: #666;
                font-size: 14px;
            }
            .template-info {
                background: #e9ecef;
                padding: 10px;
                border-radius: 4px;
                margin-bottom: 10px;
            }
            .data-section {
                margin-top: 10px;
            }
            .data-label {
                font-weight: bold;
                color: #007bff;
                margin-bottom: 5px;
            }
            .data-content {
                background: #f8f9fa;
                padding: 10px;
                border-radius: 4px;
                font-family: monospace;
                white-space: pre-wrap;
                word-break: break-all;
            }
            .success {
                color: #28a745;
            }
            .clear-btn {
                background: #dc3545;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                cursor: pointer;
                margin-bottom: 20px;
            }
            .clear-btn:hover {
                background: #c82333;
            }
            .empty {
                text-align: center;
                color: #666;
                padding: 40px;
            }
        </style>
    </head>
    <body>
        <h1>🔬 Instrument Data Forward Test Receiver</h1>
        
        <div class="status">
            <strong>✓ Server is running</strong><br>
            Endpoint: <code>POST /receive</code><br>
            Received: <span id="count">0</span> items
        </div>
        
        <button class="clear-btn" onclick="clearData()">Clear Data</button>
        
        <div id="data-list">
            <div class="empty">Waiting for data...</div>
        </div>
        
        <script>
            function loadData() {
                fetch('/data')
                    .then(response => response.json())
                    .then(data => {
                        document.getElementById('count').textContent = data.length;
                        const list = document.getElementById('data-list');
                        if (data.length === 0) {
                            list.innerHTML = '<div class="empty">Waiting for data...</div>';
                        } else {
                            list.innerHTML = data.reverse().map(item => {
                                const parsed = JSON.stringify(item.parsed_data, null, 2);
                                return `
                                    <div class="data-item">
                                        <div class="data-header">
                                            <span class="success">✓ Received</span>
                                            <span class="timestamp">${item.received_at}</span>
                                        </div>
                                        <div class="template-info">
                                            <strong>Template:</strong> ${item.template_title || 'N/A'}<br>
                                            <strong>Instrument:</strong> ${item.instrument_title || 'N/A'}
                                        </div>
                                        <div class="data-section">
                                            <div class="data-label">Raw data:</div>
                                            <div class="data-content">${item.raw_data}</div>
                                        </div>
                                        <div class="data-section">
                                            <div class="data-label">Parsed data:</div>
                                            <div class="data-content">${parsed}</div>
                                        </div>
                                    </div>
                                `;
                            }).join('');
                        }
                    });
            }
            
            function clearData() {
                if (confirm('Clear all data?')) {
                    fetch('/clear', {method: 'POST'})
                        .then(() => loadData());
                }
            }
            
            loadData();
            setInterval(loadData, 3000);
        </script>
    </body>
    </html>
    """
    return html


@app.route('/receive', methods=['POST', 'PUT'])
def receive():
    """接收转发的数据"""
    try:
        print("=" * 50)
        print("[%s] Request received" % datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        print("  Method: %s" % request.method)
        print("  Content-Type: %s" % request.headers.get('Content-Type'))
        print("  Content-Length: %s" % request.content_length)
        
        data = {}
        
        # 处理请求体 - Python 2.7 编码兼容
        request_body = request.data
        if request_body:
            # 尝试用 UTF-8 解码
            try:
                request_body_str = request_body.decode('utf-8')
            except UnicodeDecodeError:
                # 如果 UTF-8 失败，尝试用 latin-1
                request_body_str = request_body.decode('latin-1')
            print("  Raw body: %s" % request_body_str)
            
            # 解析 JSON
            try:
                data = json.loads(request_body_str)
                print("  Parsed JSON: %s" % data)
            except Exception as je:
                print("  JSON parse error: %s" % je)
                data = {"raw_body": request_body_str}
        elif request.form:
            data = request.form.to_dict()
            print("  Form data: %s" % data)
        
        received_item = {
            'received_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'timestamp': data.get('timestamp'),
            'template_uid': data.get('template_uid'),
            'template_title': data.get('template_title'),
            'instrument_uid': data.get('instrument_uid'),
            'instrument_title': data.get('instrument_title'),
            'raw_data': data.get('raw_data', ''),
            'parsed_data': data.get('parsed_data'),
            'headers': dict(request.headers),
        }
        
        received_data.append(received_item)
        
        print("  Template: %s" % received_item['template_title'])
        print("  Instrument: %s" % received_item['instrument_title'])
        print("  Raw data: %s" % received_item['raw_data'])
        print("=" * 50)
        
        response = {
            'success': True,
            'message': 'Received!',
            'received_at': received_item['received_at'],
        }
        print("  Response: %s" % json.dumps(response))
        
        return jsonify(response), 200
        
    except Exception as e:
        print("Receive error: %s" % str(e))
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': str(e),
        }), 400


@app.route('/data', methods=['GET'])
def get_data():
    """获取所有接收到的数据"""
    return jsonify(received_data)


@app.route('/clear', methods=['POST'])
def clear_data():
    """清空数据"""
    global received_data
    received_data = []
    return jsonify({'success': True, 'message': 'Data cleared'})


@app.route('/health', methods=['GET'])
def health():
    """健康检查"""
    return jsonify({
        'status': 'ok',
        'received_count': len(received_data),
    })


def main():
    """启动服务器"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Instrument Data Forward Test Receiver')
    parser.add_argument('--host', default='0.0.0.0', help='Host address (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=5000, help='Port number (default: 5000)')
    parser.add_argument('--debug', action='store_true', help='Debug mode')
    
    args = parser.parse_args()
    
    print("=" * 50)
    print("Instrument Data Forward Test Receiver")
    print("=" * 50)
    print("Listening: http://%s:%d" % (args.host, args.port))
    print("Endpoint: http://%s:%d/receive" % (args.host, args.port))
    print("Web UI: http://%s:%d/" % (args.host, args.port))
    print("=" * 50)
    print("Waiting for data...\n")
    
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == '__main__':
    main()
