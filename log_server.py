from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import os
import json
import threading


finalize_timer = None
FINALIZE_DELAY = 3.0  # seconds to wait after last request

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Global deviceNamesList array
deviceNamesList = []
# Global object to store messages grouped by device name
deviceMessages = {}

# Create logs directory if it doesn't exist
LOGS_DIR = "logs"
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

LOG_FILE = os.path.join(LOGS_DIR, "ophyd_socket_logs.txt")

def extract_device_name_from_message(data):
    """Extract device name from message data"""
    # Try different possible locations for the device name
    if 'pv' in data:
        return data['pv']
    elif 'obj' in data:
        return data['obj']
    elif 'update' in data and 'pv' in data['update']:
        return data['update']['pv']
    elif 'update' in data and 'obj' in data['update']:
        return data['update']['obj']
    return None

def finalize_device_names_delayed():
    global deviceNamesList, deviceMessages
    
    if len(deviceNamesList) == 0:
        return
    
    timestamp = datetime.now().isoformat()
    
    # Create the device names list section
    deviceNames_log_entry = f"""
=== COMPLETE DEVICE NAMES LIST (AUTO-FINALIZED) ===
Timestamp: {timestamp}
Total entries: {len(deviceNamesList)}
Complete List:
{json.dumps(deviceNamesList, indent=2)}
{'=' * 50}

"""
    
    # Create the device messages section
    deviceMessages_log_entry = f"""
=== COMPLETE DEVICE MESSAGES LIST (AUTO-FINALIZED) ===
Timestamp: {timestamp}
"""
    
    for device_name, messages in deviceMessages.items():
        deviceMessages_log_entry += f"\n{device_name}:\n"
        deviceMessages_log_entry += "{\n"
        for i, message in enumerate(messages):
            if i > 0:
                deviceMessages_log_entry += ",\n"
            deviceMessages_log_entry += f"  {{\n"
            deviceMessages_log_entry += f"    Timestamp: {message['timestamp']}\n"
            deviceMessages_log_entry += f"    Session ID: {message['sessionId']}\n"
            deviceMessages_log_entry += f"    Data:\n"
            deviceMessages_log_entry += f"    {json.dumps(message['data'], indent=4)}\n"
            deviceMessages_log_entry += f"  }}"
        deviceMessages_log_entry += "\n}\n"
    
    deviceMessages_log_entry += f"\n{'=' * 50}\n\n"
    
    # Write both sections to file
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(deviceNames_log_entry)
        f.write(deviceMessages_log_entry)
    
    print(f"Auto-finalized deviceNamesList with {len(deviceNamesList)} entries")
    print(f"Auto-finalized deviceMessages with {len(deviceMessages)} device groups")


@app.route('/log', methods=['POST'])
def write_log():
    global deviceMessages
    
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        # Extract device name from the message
        device_name = extract_device_name_from_message(data.get('data', {}))
        
        # Format the log entry
        timestamp = datetime.now().isoformat()
        log_entry = f"""
=== {data.get('label', 'UNKNOWN')} ===
Timestamp: {timestamp}
Session ID: {data.get('sessionId', 'unknown')}
Data:
{json.dumps(data.get('data', {}), indent=2)}
{'=' * 50}

"""
        
        # Store message in deviceMessages object if device name found
        if device_name:
            message_obj = {
                'timestamp': timestamp,
                'sessionId': data.get('sessionId', 'unknown'),
                'data': data.get('data', {}),
                'label': data.get('label', 'UNKNOWN')
            }
            
            if device_name not in deviceMessages:
                deviceMessages[device_name] = []
            deviceMessages[device_name].append(message_obj)
        
        # Write to file
        # with open(LOG_FILE, 'a', encoding='utf-8') as f:
        #     f.write(log_entry)
        
        return jsonify({"status": "success", "message": "Log written successfully"}), 200
        
    except Exception as e:
        print(f"Error writing log: {str(e)}")
        return jsonify({"error": str(e)}), 500
    
@app.route('/log_deviceNames', methods=['POST'])
def write_deviceName_log():
    global deviceNamesList, finalize_timer
    
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        # Cancel existing timer if it exists
        if finalize_timer:
            finalize_timer.cancel()
        
        # Extract the device names from the data array and append to global list
        device_names_batch = data.get('data', [])
        for device_name in device_names_batch:
            # Only add non-empty strings
            if device_name and device_name.strip():
                deviceNamesList.append(device_name.strip())
        
        print(f"Received batch with {len(device_names_batch)} device names")
        print(f"Current total deviceNamesList count: {len(deviceNamesList)}")
        
        # Set a timer to finalize after X seconds of no new requests
        finalize_timer = threading.Timer(FINALIZE_DELAY, finalize_device_names_delayed)
        finalize_timer.start()
        
        return jsonify({"status": "success", "message": "Batch logged successfully", "deviceNamesCount": len(deviceNamesList)}), 200
        
    except Exception as e:
        print(f"Error writing log: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/logs', methods=['GET'])
def get_logs():
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
            return jsonify({"logs": content}), 200
        else:
            return jsonify({"logs": "No logs found"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/logs', methods=['DELETE'])
def clear_logs():
    global deviceNamesList, deviceMessages
    
    try:
        if os.path.exists(LOG_FILE):
            os.remove(LOG_FILE)
        # Also clear both data structures when logs are cleared
        deviceNamesList = []
        deviceMessages = {}
        return jsonify({"status": "success", "message": "Logs cleared, deviceNamesList and deviceMessages reset"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/deviceNames', methods=['GET'])
def get_device_names():
    """Endpoint to get the current deviceNamesList"""
    return jsonify({"deviceNamesList": deviceNamesList, "count": len(deviceNamesList)}), 200

@app.route('/deviceMessages', methods=['GET'])
def get_device_messages():
    """New endpoint to get the current deviceMessages object"""
    return jsonify({"deviceMessages": deviceMessages, "deviceCount": len(deviceMessages)}), 200

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()}), 200

if __name__ == '__main__':
    print(f"Starting log server...")
    print(f"Logs will be written to: {os.path.abspath(LOG_FILE)}")
    app.run(host='0.0.0.0', port=3001, debug=True)