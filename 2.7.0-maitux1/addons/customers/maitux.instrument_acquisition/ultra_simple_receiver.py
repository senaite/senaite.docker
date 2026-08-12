# -*- coding: utf-8 -*-
"""
超级简单的测试接收器 - 零编码问题
"""
from flask import Flask, request, jsonify
from datetime import datetime
import json

app = Flask(__name__)


@app.route('/', methods=['GET'])
def index():
    return "OK - Server is running! Use POST /receive"


@app.route('/receive', methods=['POST', 'PUT', 'GET'])
def receive():
    print("=" * 50)
    print("[%s] Request received" % datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print("  Method: %s" % request.method)
    
    # 直接读取原始字节
    raw_data = request.data
    print("  Raw data length: %d" % len(raw_data))
    print("  Raw data: %r" % raw_data)
    
    # 构建响应
    response = {
        'success': True,
        'message': 'OK',
        'received_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    
    print("  Response: %s" % json.dumps(response))
    print("=" * 50)
    
    return jsonify(response)


if __name__ == '__main__':
    print("=" * 50)
    print("Ultra Simple Test Receiver")
    print("=" * 50)
    print("Listening: http://0.0.0.0:5002")
    print("Endpoint: http://0.0.0.0:5002/receive")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5002, debug=True)
