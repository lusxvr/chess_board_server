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
            sio.emit('update_board', {
                'board': game.get_board(),
                'turn': game.get_turn(),
                'last_move': game.get_last_move()
            })
            
            # Process the physical move in a separate thread
            # BUT do not link it to the black move monitoring
            physical_command = cv.chess_to_physical_coords(move)
            threading.Thread(
                target=execute_physical_move,
                args=(physical_command,),
                daemon=True
            ).start()
            
            # Return success immediately
            return jsonify({'success': True, 'board': game.get_board()})

    return jsonify({'success': False})

def execute_physical_move(physical_command):
    """Simply execute a physical move without any dependencies."""
    try:
        print(f"Executing physical move: {physical_command}")
        arduino.send_command(physical_command)
        print("✅ Physical move sent to Arduino")
    except Exception as e:
        print(f"❌ Error during physical move: {e}")

# Completely separate function to monitor black's turn
# This should run continuously in the background
def start_continuous_monitoring():
    """Start a continuous background monitoring process."""
    threading.Thread(
        target=continuous_board_monitor,
        daemon=True
    ).start()
    print("🔄 Started continuous board monitoring")

def continuous_board_monitor():
    """Continuously monitor the board state for changes."""
    last_known_state = None
    last_turn = None
    
    while True:
        try:
            current_turn = game.get_turn()
            
            # Only monitor when it's black's turn
            if current_turn == "black":
                # If we just switched to black's turn, reset our state
                if last_turn != "black":
                    print("👁️ Black's turn - starting to monitor physical board")
                    time.sleep(2)  # Give time for physical move to complete
                    last_known_state = get_current_board_state(verbose=True)
                    if not last_known_state:
                        print("❌ Could not read initial board state")
                        time.sleep(1)
                        continue
                    print("✅ Initial black board state captured")
                
                # We have a valid last state, check for changes
                if last_known_state:
                    current_state = get_current_board_state(verbose=False)
                    if not current_state:
                        time.sleep(0.5)
                        continue
                    
                    # Check if a move was made
                    move = arduino.detect_move(last_known_state, current_state)
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
                            
                            # Reset state for next turn
                            last_known_state = None
            
            # Update last turn
            last_turn = current_turn
            
            # Brief pause before next check
            time.sleep(0.5)
            
        except Exception as e:
            print(f"❌ Error in board monitor: {e}")
            time.sleep(1)

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
        
        # Start continuous board monitoring
        start_continuous_monitoring()
        
        print("🚀 Starting server...")
        eventlet.wsgi.server(eventlet.listen(('127.0.0.1', 5000)), app)
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        # Make sure to close Arduino connection when server stops
        arduino.close()

