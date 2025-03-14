from flask import Flask, render_template, request, jsonify
import socketio
import eventlet
import converter as cv
from board import game
from arduino_controller import ArduinoController
import time
import threading

app = Flask(__name__)

# Create SocketIO server with eventlet
sio = socketio.Server(cors_allowed_origins="*")
app.wsgi_app = socketio.WSGIApp(sio, app.wsgi_app)

# Initialize Arduino controller globally
arduino = ArduinoController()

# Track active threads to avoid duplicate monitoring
active_black_monitoring = False

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
    """Handle moves from the web interface (white's moves)."""
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
            
            # Execute white's physical move in a thread
            physical_command = cv.chess_to_physical_coords(move)
            white_thread = threading.Thread(
                target=execute_white_move,
                args=(physical_command,),
                daemon=True
            )
            white_thread.start()
            
            return jsonify({'success': True, 'board': game.get_board()})

    return jsonify({'success': False})

def execute_white_move(physical_command):
    """Execute white's physical move on the Arduino (runs in a thread)."""
    try:
        print(f"Executing physical move: {physical_command}")
        arduino.send_command(physical_command)
        print("✅ Physical move sent to Arduino")
        
        # Optional: Wait for move completion
        if arduino.wait_for_move_completion():
            print("✅ Physical move completed")
        
        # After white's move completes, start monitoring for black's move
        if game.get_turn() == "black":
            start_black_turn_monitoring()
            
    except Exception as e:
        print(f"❌ Error during physical move: {e}")

def start_black_turn_monitoring():
    """Start monitoring for black's physical move."""
    global active_black_monitoring
    
    # Avoid starting multiple monitoring threads
    if active_black_monitoring:
        return
        
    active_black_monitoring = True
    black_thread = threading.Thread(
        target=monitor_black_turn,
        daemon=True
    )
    black_thread.start()
    print("👁️ Started monitoring for black's move")

def monitor_black_turn():
    """Monitor the physical board for black's move (runs in a thread)."""
    global active_black_monitoring
    
    try:
        print("🔍 Monitoring physical board for black's move...")
        
        # Take an initial snapshot of the board
        initial_state = get_current_board_state(verbose=True)
        if not initial_state:
            print("❌ Could not read initial board state")
            active_black_monitoring = False
            return
        
        print("✅ Initial board state captured, waiting for move...")
        
        # Poll until we detect a change or it's no longer Black's turn
        attempts = 0
        max_attempts = 1200  # 10 minutes at 0.5s intervals
        
        while game.get_turn() == "black" and attempts < max_attempts:
            # Wait a moment between checks
            time.sleep(0.5)
            attempts += 1
            
            # Print waiting message less frequently
            if attempts % 60 == 0:
                print(f"Still waiting for black's move... ({attempts/2} seconds)")
            
            # Read current state silently
            current_state = get_current_board_state(verbose=False)
            if not current_state:
                continue
            
            # Check if a move was made
            move = arduino.detect_move(initial_state, current_state)
            if move:
                print(f"💡 Detected black's move: {move}")
                
                # Process the move
                start = (6 - int(move[1]), ord(move[0]) - ord('a'))
                end = (6 - int(move[4]), ord(move[3]) - ord('a'))
                
                if game.move(start, end):
                    print(f"✅ Black's move applied: {move}")
                    
                    # IMMEDIATELY broadcast the updated board
                    sio.emit('update_board', {
                        'board': game.get_board(),
                        'turn': game.get_turn(),
                        'last_move': game.get_last_move()
                    })
                    break
                else:
                    print("❌ Invalid move detected")
        
        if attempts >= max_attempts:
            print("⚠️ Timed out waiting for black's move")
            
    except Exception as e:
        print(f"❌ Error monitoring black's move: {e}")
    finally:
        active_black_monitoring = False

def get_current_board_state(verbose=False):
    """Helper function to get board state matrix from Arduino."""
    try:
        # Read state from Arduino
        state_string = arduino.read_board_state(verbose)
        
        if state_string and len(state_string) == 36:
            return arduino.board_state_to_matrix(state_string)
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

