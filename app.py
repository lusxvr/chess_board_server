from flask import Flask, render_template, request, jsonify
import socketio
import eventlet
import converter as cv
from board import game
from arduino_controller import ArduinoController
import time

app = Flask(__name__)

# Create SocketIO server with eventlet
sio = socketio.Server(cors_allowed_origins="*")
app.wsgi_app = socketio.WSGIApp(sio, app.wsgi_app)

# Initialize Arduino controller globally
arduino = ArduinoController()

# Create a flag to track if we're already monitoring the board
monitoring_black_moves = False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/board', methods=['GET'])
def get_board():
    """Returns the current state of the board as JSON."""
    return jsonify({
        'board': game.get_board(),
        'turn': game.get_turn()
    })

@app.route('/move', methods=['POST'])
def make_move():
    """Handle moves from the web interface (White's moves)."""
    move = request.form['move'].strip()
    print(f"Move received: {move}")
    
    if len(move) == 5 and move[2] == ' ':
        start = (6 - int(move[1]), ord(move[0]) - ord('a'))
        end = (6 - int(move[4]), ord(move[3]) - ord('a'))

        if game.move(start, end):
            # IMMEDIATELY broadcast the updated board to all clients
            # This ensures the web interface updates right away
            sio.emit('update_board', {
                'board': game.get_board(),
                'turn': game.get_turn(),
                'last_move': game.get_last_move()
            })
            
            # Convert chess move to physical coordinates
            physical_command = cv.chess_to_physical_coords(move)
            print(f"Physical command: {physical_command}")
            
            try:
                # Send command to Arduino
                arduino.send_command(physical_command)
                print("✅ Move command sent to Arduino")
                
                # Wait for Arduino to complete the move
                if arduino.wait_for_move_completion():
                    print("✅ Physical move completed")
                else:
                    print("⚠️ Timeout waiting for move completion")
            except Exception as e:
                print(f"❌ Failed to send command to Arduino: {e}")
            
            # If it's now black's turn, start monitoring the physical board in background
            if game.get_turn() == "black":
                start_black_move_monitoring()
                
            return jsonify({'success': True, 'board': game.get_board()})

    return jsonify({'success': False})

def start_black_move_monitoring():
    """Start monitoring for black's move in a non-blocking background task."""
    global monitoring_black_moves
    
    # Avoid starting multiple monitoring tasks
    if monitoring_black_moves:
        print("👁️ Already monitoring physical board")
        return
    
    print("👁️ Black's turn - starting background monitoring of physical board")
    monitoring_black_moves = True
    
    # Start monitoring in a background task using eventlet
    eventlet.spawn(monitor_black_move)

def monitor_black_move():
    """Background task that monitors the physical board for black's move."""
    global monitoring_black_moves
    
    try:
        print("🔍 Starting to monitor physical board for black's move...")
        
        # Take an initial snapshot of the board
        initial_state = get_current_board_state(verbose=True)  # Verbose for initial state
        if not initial_state:
            print("❌ Could not read initial board state")
            monitoring_black_moves = False
            return
        
        print("✅ Initial board state captured, waiting for move...")
        
        # Poll until we detect a change or it's no longer Black's turn
        attempts = 0
        max_attempts = 600  # 10 minutes at 1s intervals
        
        while game.get_turn() == "black" and attempts < max_attempts:
            # Wait a moment between checks
            eventlet.sleep(1)  # Use eventlet.sleep instead of time.sleep
            attempts += 1
            
            # Print waiting message less frequently
            if attempts % 30 == 0:
                print(f"Still waiting for physical move... ({attempts} seconds / {max_attempts} seconds)")
            
            # Read current state silently (non-verbose)
            current_state = get_current_board_state(verbose=False)
            if not current_state:
                continue  # Skip this iteration if read failed
            
            # Check if a move was made
            move = arduino.detect_move(initial_state, current_state)
            if move:
                # When a change is detected, print the current state
                print(f"💡 Board state changed: {arduino.matrix_to_string(current_state)}")
                print(f"Detected move from physical board: {move}")
                
                # Parse chess notation to board coordinates
                start_file, start_rank = move[0], move[1]
                end_file, end_rank = move[3], move[4]
                
                start = (6 - int(start_rank), ord(start_file) - ord('a'))
                end = (6 - int(end_rank), ord(end_file) - ord('a'))
                
                if game.move(start, end):
                    print(f"✅ Move applied: {move}")
                    # Broadcast the updated board to all connected clients
                    sio.emit('update_board', {
                        'board': game.get_board(),
                        'turn': game.get_turn(),
                        'last_move': game.get_last_move()
                    })
                    break  # Exit the loop after a successful move
                else:
                    print("❌ Invalid move detected from physical board")
        
        if game.get_turn() == "black":
            print("⚠️ Timed out waiting for physical move")
    
    finally:
        # Always reset the monitoring flag when done
        monitoring_black_moves = False
        print("👁️ Stopped monitoring physical board")

# WebSocket events
@sio.event
def connect(sid, environ):
    print(f"✅ Client {sid} connected")
    # Send current game state to new client
    sio.emit('update_board', {
        'board': game.get_board(),
        'turn': game.get_turn()
    }, room=sid)

@sio.event
def disconnect(sid):
    print(f"❌ Client {sid} disconnected")

@sio.on('move_from_real_board')
def handle_move(sid, data):
    """Handle moves sent from the web client that were detected on the physical board."""
    move = data['move']
    print(f"📥 Move received from client {sid}: {move}")

    if len(move) == 5 and move[2] == ' ':
        start = (6 - int(move[1]), ord(move[0]) - ord('a'))
        end = (6 - int(move[4]), ord(move[3]) - ord('a'))

        if game.move(start, end):
            print(f"✅ Move applied: {move}")
            
            # IMMEDIATELY broadcast the updated board to all connected clients
            sio.emit('update_board', {
                'board': game.get_board(),
                'turn': game.get_turn(),
                'last_move': game.get_last_move()
            })
            
            # If it's now black's turn, start monitoring in the background
            if game.get_turn() == "black":
                start_black_move_monitoring()
        else:
            print("❌ Invalid move")
            sio.emit('move_rejected', {'message': 'Invalid move'}, room=sid)
    else:
        print("❌ Incorrect move format")
        sio.emit('move_rejected', {'message': 'Incorrect move format'}, room=sid)

def get_current_board_state(verbose=False):
    """
    Helper function to get board state matrix from Arduino
    
    Args:
        verbose (bool): Whether to print verbose output
    """
    try:
        # Read state from Arduino
        state_string = arduino.read_board_state(verbose)
        
        if state_string and len(state_string) == 36:
            matrix = arduino.board_state_to_matrix(state_string)
            if verbose:
                print(f"Board state: {state_string}")
            return matrix
        else:
            if verbose:
                print(f"Failed to get valid board state (received: {state_string})")
            return None
    except Exception as e:
        if verbose:
            print(f"Error reading board state: {e}")
        return None

def debug_arduino_communication():
    """Direct debugging function for Arduino communication"""
    print("🔍 DEBUGGING: Sending READ_BOARD command...")
    
    # Clear any existing data
    arduino.serial.reset_input_buffer()
    arduino.serial.reset_output_buffer()
    
    # Send command with proper line ending
    arduino.serial.write(b"READ_BOARD\n")
    arduino.serial.flush()
    
    # Wait for Arduino to process
    time.sleep(1)
    
    # Check if data is available
    available = arduino.serial.in_waiting
    print(f"🔍 DEBUGGING: Bytes available to read: {available}")
    
    if available > 0:
        # Read raw response
        raw_response = arduino.serial.readline()
        print(f"🔍 DEBUGGING: Raw bytes received: {raw_response}")
        
        # Try to decode
        try:
            decoded = raw_response.decode().strip()
            print(f"🔍 DEBUGGING: Decoded response: '{decoded}'")
            print(f"🔍 DEBUGGING: Response length: {len(decoded)}")
        except Exception as e:
            print(f"🔍 DEBUGGING: Error decoding response: {e}")
    else:
        print("🔍 DEBUGGING: No data received from Arduino")

# Update arduino_controller.py to have this method
# def wait_for_move_completion(self, timeout=30):
#     """Wait for the Arduino to complete a move"""
#     start_time = time.time()
#     while time.time() - start_time < timeout:
#         if self.serial.in_waiting > 0:
#             response = self.serial.readline().decode().strip()
#             if response == "MOVE_COMPLETE":
#                 return True
#         time.sleep(0.1)
#     return False

if __name__ == '__main__':
    try:
        # Connect to Arduino before starting server
        print("🔌 Connecting to Arduino...")
        arduino.connect()
        
        print("🚀 Starting server...")
        eventlet.wsgi.server(eventlet.listen(('127.0.0.1', 5000)), app)
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        # Make sure to close Arduino connection when server stops
        arduino.close()

